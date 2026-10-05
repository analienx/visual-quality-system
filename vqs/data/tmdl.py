"""Static semantic-model facts from TMDL declarations (WP-05 subset, issue #10).

Parses `table` / `column` / `measure` declarations from `*.tmdl` text —
including multiline expressions, calculated-column expressions, quoted and
dotted identifiers, and `//` comments — and cross-checks PBIR field
bindings (`queryRef`) against the declared model: unknown tables or fields
become fail findings, measures without a recorded expression become
``unknown``. Live values, refresh identity, RLS scoping, and DAX execution
are NOT performed here — absent data facts are reported ``blocked`` via
:func:`blocked_snapshot`, never fabricated.

This module is the single shared TMDL extractor: the cycle gate, the
measure emitter, and the insight inventory all build on
:func:`extract_objects` instead of running divergent readers.
"""
from __future__ import annotations

import re
from pathlib import Path

#: TMDL member properties collected into per-object property maps.
KNOWN_PROPERTIES = frozenset({
    "formatString", "description", "displayFolder", "dataType",
    "dataCategory", "expression", "isHidden", "isUnique", "isKey",
    "lineageTag", "sourceColumn", "sortByColumn", "summarizeBy",
    "sourceProviderType", "isAvailableInMdx",
})

_PROPERTY = re.compile(r"^([A-Za-z][\w]*)\s*:\s*(.*)$")


def _unquote(name: str) -> str:
    """Strip one matching quote layer; doubled-quote escapes unescaped."""
    if len(name) >= 2 and name[0] == name[-1] and name[0] in ("'", '"'):
        quote = name[0]
        return name[1:-1].replace(quote * 2, quote)
    return name


def _strip_comment(line: str) -> str:
    """Remove a // comment outside any quoted span (single-quote, double,
    or triple-double). Triple-quote state does not leak across lines here;
    multiline values are joined before this runs."""
    out: list[str] = []
    index, size = 0, len(line)
    quote: str | None = None
    while index < size:
        # F12: triple-backtick DAX stays verbatim; // inside it
        # is DAX text, never a TMDL comment.
        if quote is None and line.startswith('```', index):
            quote = '```'
            out.append('```')
            index += 3
        elif quote == '```' and line.startswith('```', index):
            quote = None
            out.append('```')
            index += 3
        elif quote == '```':
            out.append(line[index])
            index += 1
        elif quote is None and line.startswith('"""', index):
            quote = '"""'
            out.append('"""')
            index += 3
        elif quote == '"""' and line.startswith('"""', index):
            quote = None
            out.append('"""')
            index += 3
        elif quote == '"""':
            out.append(line[index])
            index += 1
        elif quote is None and line[index] in ("'", '"'):
            quote = line[index]
            out.append(line[index])
            index += 1
        elif quote in ("'", '"') and line[index] == quote:
            if line[index + 1:index + 2] == quote:
                out.append(quote * 2)
                index += 2
            else:
                quote = None
                out.append(line[index])
                index += 1
        elif quote is None and line.startswith("//", index):
            break
        else:
            out.append(line[index])
            index += 1
    return "".join(out)


def _span_opener(text: str) -> str | None:
    """First multiline-span opener on a line: ``` or triple-quote."""
    tick = text.find("```")
    quote = text.find('"""')
    if tick == -1:
        return '"""' if quote != -1 else None
    if quote == -1:
        return "```"
    return "```" if tick < quote else '"""'


def _strip_backticks(expr: str) -> tuple[str, bool]:
    """Drop triple-backtick delimiters; (content, unclosed-fence flag).

    An opening fence with no closer records nothing: the expression is
    unparseable and must block downstream instead of parsing through.
    """
    text = expr.strip()
    if not text.startswith("```"):
        return text, False
    inner = text[3:]
    end = inner.rfind("```")
    if end == -1:
        return "", True
    return inner[:end].strip(), False


def _join_triples(lines: list[str]) -> tuple[list[str], list[int], list[int]]:
    """Join \"\"\"-quoted spans into logical lines (F12: triple-backtick and triple-quote).

    Returns (logical lines, 1-based start line per logical line,
    unterminated span starts). Unterminated spans keep their gathered
    text and are reported as issues by the caller.
    """
    logical: list[str] = []
    starts: list[int] = []
    unterminated: list[int] = []
    index = 0
    while index < len(lines):
        start = index + 1
        text = lines[index]
        opener = _span_opener(text)
        if opener is not None and text.count(opener) % 2 == 1:
            gathered = [text]
            index += 1
            while index < len(lines) and opener not in lines[index]:
                gathered.append(lines[index])
                index += 1
            if index < len(lines):
                gathered.append(lines[index])
            else:
                unterminated.append(start)
            logical.append("\n".join(gathered))
            starts.append(start)
        else:
            logical.append(text)
            starts.append(start)
        index += 1
    return logical, starts, unterminated


def _split_declaration(rest: str) -> tuple[str, str, str]:
    """Split a member declaration at the first = outside quotes.

    Quoted identifiers may contain = (F11); doubled quotes stay
    quoted. Returns (name, sep, expression) like str.partition.
    """
    quote: str | None = None
    index, size = 0, len(rest)
    while index < size:
        char = rest[index]
        if quote is None and char in ("'", '"'):
            quote = char
        elif quote is not None and char == quote:
            if rest[index + 1:index + 2] == quote:
                index += 1
            else:
                quote = None
        elif quote is None and char == "=":
            return rest[:index], "=", rest[index + 1:]
        index += 1
    return rest, "", ""


def _indent_of(line: str) -> int:
    stripped = line.lstrip(" \t")
    return len(line.expandtabs(8)) - len(stripped.expandtabs(8)) if stripped else -1


def _is_table(stripped: str) -> bool:
    """Case-insensitive ``table `` keyword (TMDL keywords have no case)."""
    return stripped[:6].casefold() == "table "


def _is_member(stripped: str) -> bool:
    """Case-insensitive ``measure ``/``column `` keyword."""
    return (stripped[:8].casefold() == "measure "
            or stripped[:7].casefold() == "column ")


def extract_objects(text: str) -> dict:
    """Extract tables/measures/columns with expressions and properties.

    Handles tab- or space-indented files, `measure`/`column` declarations
    with `=` expressions (single- or multi-line via deeper-indented
    continuation), `expression:` calculated-column properties,
    triple-quoted values, and `//` comments. Malformed lines become
    issues, never raises. Non-table top-level objects are skipped.
    """
    tables: dict[str, dict] = {}
    issues: list[dict] = []
    logical, starts, unterminated = _join_triples(text.splitlines())
    for lineno in unterminated:
        issues.append({"rule": "unterminated_multiline", "line": lineno})
    current: str | None = None
    seen_top = False
    member: tuple[str, str] | None = None
    member_indent = 0
    annotation_indent: int | None = None
    continuation: list[str] = []

    def flush() -> None:
        nonlocal continuation
        if member is not None and continuation and current is not None:
            kind, name = member
            extra = "\n".join(continuation).strip()
            if extra:
                prior = tables[current][kind + "s"][name]
                tables[current][kind + "s"][name] = (
                    f"{prior}\n{extra}" if prior else extra)
        continuation = []

    for lineno, raw in zip(starts, logical):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = _indent_of(line)
        if indent == 0:
            flush()
            member = None
            annotation_indent = None
            seen_top = True
            stripped = line.strip()
            if _is_table(stripped):
                name = _unquote(stripped[6:].strip())
                if not name:
                    issues.append({"rule": "empty_table_name", "line": lineno})
                    current = None
                else:
                    current = name
                    tables.setdefault(current, {"measures": {}, "columns": {},
                                                "measure_props": {}, "column_props": {}})
            else:
                current = None
            continue
        if current is None:
            if not seen_top and _is_member(line.strip()):
                issues.append({"rule": "orphan_declaration", "line": lineno})
            continue
        stripped = line.strip()
        if member is not None and indent > member_indent:
            if stripped == "annotation" or stripped.startswith(
                    ("annotation ", "annotation\t")):
                annotation_indent = indent
                continue
            if annotation_indent is not None:
                if indent > annotation_indent:
                    continue
                annotation_indent = None
            match = _PROPERTY.match(stripped)
            if match:
                if match.group(1) in KNOWN_PROPERTIES:
                    flush()
                    _record_prop(tables[current], member, match.group(1),
                                 match.group(2).strip())
                # Any other `name:` line is a (possibly unknown)
                # property, never DAX expression text.
                continue
            continuation.append(stripped)
            continue
        flush()
        member = None
        annotation_indent = None
        if _is_member(stripped):
            kind = ("measure" if stripped[:8].casefold() == "measure "
                    else "column")
            rest = stripped[len(kind) + 1:]
            name, sep, expression = _split_declaration(rest)
            name = _unquote(name.strip())
            member = (kind, name)
            member_indent = indent
            if sep:
                body, unclosed = _strip_backticks(expression)
                if unclosed:
                    issues.append({"rule": "unclosed_backtick",
                                   "line": lineno, "table": current,
                                   "member": name})
                    member = None
                    continue
            else:
                body = ""
            tables[current][kind + "s"][name] = body
            tables[current][kind + "_props"].setdefault(name, {})
        # Other member-level lines (lineageTag, annotations, ...) are
        # table metadata, not declarations; skipped, not flagged.
    flush()
    return {"tables": tables, "issues": issues}


def _record_prop(table: dict, member: tuple[str, str], prop: str, value: str) -> None:
    kind, name = member
    table[kind + "_props"].setdefault(name, {})[prop] = value
    if prop == "expression":
        prior = table[kind + "s"].get(name, "")
        table[kind + "s"][name] = f"{prior}\n{value}".strip() if prior else value


def parse_tmdl(text: str) -> dict:
    """Parse TMDL table declarations; malformed lines become issues, never raises.

    Real-world files use quoted identifiers (``table 'Fact Sales'``) and
    non-table top-level objects (``model``, ``relationship``,
    ``expression``); quoted names are unquoted for binding comparison and
    non-table subtrees are skipped, not flagged. Only a ``measure`` or
    ``column`` line before any top-level object is an orphan.
    """
    extracted = extract_objects(text)
    tables = {}
    for name, content in extracted["tables"].items():
        tables[name] = {"measures": dict(content["measures"]),
                        "columns": dict(content["columns"]),
                        "measure_props": {k: dict(v) for k, v in content["measure_props"].items()},
                        "column_props": {k: dict(v) for k, v in content["column_props"].items()}}
    return {"tables": tables, "issues": extracted["issues"]}


def inventory_model(model_dir: Path) -> dict:
    """Inventory every `*.tmdl` file under a model directory."""
    model_dir = Path(model_dir)
    if not model_dir.is_dir():
        return {"tables": {}, "issues": [{"rule": "no_model", "path": str(model_dir)}]}
    try:
        files = sorted(model_dir.rglob("*.tmdl"))
    except OSError as exc:
        return {"tables": {}, "issues": [{"rule": "no_model", "detail": str(exc)}]}
    if not files:
        return {"tables": {}, "issues": [{"rule": "no_model", "path": str(model_dir)}]}
    merged: dict[str, dict] = {}
    issues: list[dict] = []
    for file in files:
        try:
            parsed = parse_tmdl(file.read_text(encoding="utf-8-sig"))
        except OSError as exc:
            issues.append({"rule": "unreadable_model_file", "part": file.name,
                           "detail": str(exc)})
            continue
        issues.extend({**row, "part": file.name} for row in parsed["issues"])
        for table, content in parsed["tables"].items():
            target = merged.setdefault(table, {"measures": {}, "columns": {},
                                               "measure_props": {}, "column_props": {}})
            target["measures"].update(content["measures"])
            target["columns"].update(content["columns"])
            for name, props in content["measure_props"].items():
                target["measure_props"].setdefault(name, {}).update(props)
            for name, props in content["column_props"].items():
                target["column_props"].setdefault(name, {}).update(props)
    return {"tables": merged, "issues": issues}


def split_table_field(ref: str, tables: dict) -> tuple[str | None, str | None]:
    """Split a dotted ref into (table, field) with longest-table match.

    Dotted table names resolve against the known tables first
    (``Dim.Product.Brand`` with table ``Dim.Product`` yields
    ``(Dim.Product, Brand)``); otherwise the split falls back to the
    last dot. Unparseable refs yield ``(None, None)``.
    """
    if not isinstance(ref, str):
        return None, None
    text = ref.strip()
    if not text:
        return None, None
    for table in sorted(tables, key=len, reverse=True):
        if text == table:
            return table, ""
        if text.startswith(table + "."):
            return table, text[len(table) + 1:]
    table, dot, field = text.rpartition(".")
    if not dot or not table or not field:
        return None, None
    return table, field


def _check_actual(binding: dict, ref: str, tables: dict) -> dict:
    """Resolve a structured actual (entity/property) against the model.

    T04: the actual semantic field resolves exactly — no label
    splitting, no queryRef fallback. A dangling actual fails even
    when the projection label names an existing field.
    """
    entity = binding.get("entity")
    prop = binding.get("property")
    kind = binding.get("kind", "")
    base: dict[str, object] = {"query_ref": ref}
    if isinstance(kind, str) and kind:
        base["kind"] = kind
    if isinstance(entity, str) and entity:
        base["entity"] = entity
    if isinstance(prop, str) and prop:
        base["property"] = prop
    if (not isinstance(entity, str) or not entity
            or not isinstance(prop, str) or not prop
            or entity not in tables):
        return {"rule": "missing_dimension_or_measure", "status": "fail",
                **base}
    content = tables[entity]
    if kind == "Column":
        if prop in content["columns"]:
            return {"rule": "binding_resolved", "status": "pass", **base}
        return {"rule": "missing_dimension_or_measure", "status": "fail",
                **base}
    if kind == "Aggregation" and prop in content["columns"]:
        return {"rule": "binding_resolved", "status": "pass", **base}
    if prop in content["measures"]:
        if content["measures"][prop]:
            return {"rule": "binding_resolved", "status": "pass", **base}
        return {"rule": "measure_without_expression", "status": "unknown",
                "reason": "Values require a live authorized query", **base}
    if not kind and prop in content["columns"]:
        return {"rule": "binding_resolved", "status": "pass", **base}
    return {"rule": "missing_dimension_or_measure", "status": "fail", **base}


def check_bindings(bindings: list[dict], inventory: dict) -> list[dict]:
    """Resolve PBIR projection bindings against the declared model.

    T04: structured bindings resolve their actual field expression
    (SourceRef entity + property); ``query_ref`` is projection
    identity only. ``actual_unknown`` marks unsupported expression
    coverage (``unknown``, never pass). Bare ``query_ref``-only
    bindings keep legacy label resolution for hand-fed facts; the
    PBIR producer always emits structured actuals. Dotted table
    names in legacy labels resolve via longest-table match. Unknown
    tables/fields fail; measures without a recorded expression
    are ``unknown`` — their values require a live authorized query
    (blocked).
    """
    tables = inventory.get("tables", {})
    findings = []
    for binding in bindings:
        ref = binding.get("query_ref", "") if isinstance(binding, dict) else ""
        if not isinstance(ref, str):
            ref = ""
        if isinstance(binding, dict) and binding.get("actual_unknown"):
            findings.append({"rule": "binding_expression_unsupported",
                             "status": "unknown", "query_ref": ref,
                             "reason": "Projection field expression is outside "
                                       "supported coverage"})
            continue
        if isinstance(binding, dict) and (
                "entity" in binding or "property" in binding):
            findings.append(_check_actual(binding, ref, tables))
            continue
        table, field = split_table_field(ref, tables)
        if not table or not field or table not in tables:
            findings.append({"rule": "missing_dimension_or_measure", "status": "fail",
                             "query_ref": ref})
            continue
        content = tables[table]
        if field in content["columns"]:
            findings.append({"rule": "binding_resolved", "status": "pass",
                             "query_ref": ref})
        elif field in content["measures"]:
            if content["measures"][field]:
                findings.append({"rule": "binding_resolved", "status": "pass",
                                 "query_ref": ref})
            else:
                findings.append({"rule": "measure_without_expression", "status": "unknown",
                                 "query_ref": ref,
                                 "reason": "Values require a live authorized query"})
        else:
            findings.append({"rule": "missing_dimension_or_measure", "status": "fail",
                             "query_ref": ref})
    return findings


def blocked_snapshot(reason: str) -> dict:
    """Explicit blocked data snapshot: no live query, no fabricated values."""
    return {"status": "blocked", "reason": reason, "values": None}


def check_freshness(bound_sha256: str, current_sha256: str, label: str) -> dict:
    """Fail findings bound to an out-of-date source or model snapshot.

    Covers the out-of-date-source and stale-cache legs: a fact recorded
    against one digest is invalid once the source moves, even when the
    fact itself was once correct.
    """
    if not bound_sha256 or not current_sha256:
        return {"rule": "freshness_unknown", "status": "blocked", "label": label,
                "reason": "Bound and current digests are both required"}
    if bound_sha256 != current_sha256:
        return {"rule": "stale_source", "status": "fail", "label": label,
                "bound": bound_sha256, "current": current_sha256}
    return {"rule": "freshness_ok", "status": "pass", "label": label}


def require_rls_identity(role: str) -> dict:
    """Block scoped facts without an explicit RLS identity (missing-role leg)."""
    if not isinstance(role, str) or not role.strip():
        return {"rule": "missing_rls_identity", "status": "blocked",
                "reason": "An explicit RLS role is required before scoped answers"}
    return {"rule": "rls_identity_present", "status": "pass", "role": role}
