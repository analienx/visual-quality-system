"""Static acyclicity gate for TMDL semantic models (no-cycles check).

Steps 1-2 of the handover gate, generalized from proven session
probes: parse every DAX measure/calculated column and every M query
(shared expressions plus table partitions) from a ``*.SemanticModel``
definition folder, build reference graphs, and report cycles. Pure
static analysis — no engine, no Desktop, no network. The live-engine
confirmation (step 3) stays a Modeling MCP procedure, not code here.

A returned cycle is a list of node ids forming the loop, last element
repeating the first. DAX nodes look like ``measure:Table.Name``;
M nodes are query names (``Table|Partition`` for partitions).

DAX extraction shares :mod:`vqs.data.tmdl` with the binding checker so
multiline expressions, calculated columns, and quoted identifiers parse
one way. Qualified ``'Table'[Name]`` references resolve exactly;
unsupported or unreadable model files block the gate (``OSError``)
instead of silently narrowing the graph.
"""
from __future__ import annotations

import glob
import os
import re

from vqs.data.tmdl import extract_objects

_TABLE_QUOTED = re.compile(r"^table '(.+)'$", re.MULTILINE | re.IGNORECASE)
_TABLE_BARE = re.compile(r"^table (\S+)$", re.MULTILINE | re.IGNORECASE)
_EXPRESSION = re.compile(
    r"^expression\s+('([^']+)'|([^\s=]+))\s*=\s*(.*?)(?=^expression\s|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE)
_PARTITION_M = re.compile(
    r"^\tpartition\s+('([^']+)'|([^\s=]+))\s*=\s*m\s*$(.*?)(?=^\t\S|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE)
_EXPRESSION_ANY = re.compile(
    r"^expression\s+('([^']+)'|([^\s=]+))",
    re.MULTILINE | re.IGNORECASE)
_PARTITION_ANY = re.compile(
    r"^[ \t]*partition\s+('([^']+)'|([^\s=]+))",
    re.MULTILINE | re.IGNORECASE)
_QUALIFIED = re.compile(
    r"'((?:[^']|'')+)'\s*\[([^\[\]]+)\]|([A-Za-z_][\w]*)\s*\[([^\[\]]+)\]")
_BARE_REF = re.compile(r"\[([^\[\]]+)\]")
_LET = re.compile(r"(?<![\w])let(?![\w])")
_IN = re.compile(r"(?<![\w])in(?![\w])")
_M_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def _table_name(text: str) -> str | None:
    match = _TABLE_QUOTED.search(text) or _TABLE_BARE.search(text)
    return match.group(1) if match else None


def _m_string_end(code: str, start: int) -> int:
    """Index just past a string's closing quote; -1 when unterminated."""
    index, size = start, len(code)
    while index < size:
        if code[index] == '"':
            if code[index + 1:index + 2] == '"':
                index += 2
            else:
                return index + 1
        else:
            index += 1
    return -1


def _m_quoted_content(code: str, start: int) -> tuple[str, int]:
    """Parse #"..." content from start; ("", -1) when unterminated."""
    chars: list[str] = []
    index, size = start, len(code)
    while index < size:
        if code[index] == '"':
            if code[index + 1:index + 2] == '"':
                chars.append('"')
                index += 2
            else:
                return "".join(chars), index + 1
        else:
            chars.append(code[index])
            index += 1
    return "", -1


def _m_clean(code: str) -> tuple[str, list[str]]:
    """Blank M strings/comments; mask #"quoted ids" as placeholders.

    Returns (cleaned, quoted contents in order); a placeholder looks
    like ``\\x00{i}\\x00``. Unterminated constructs stay verbatim so
    broken input yields more edges (fail closed), never fewer.
    """
    out: list[str] = []
    quoted: list[str] = []
    slots: dict[str, int] = {}
    index, size = 0, len(code)
    while index < size:
        pair = code[index:index + 2]
        if pair == "//":
            end = code.find("\n", index)
            if end == -1:
                break
            out.append(" ")
            index = end
        elif pair == "/*":
            end = code.find("*/", index + 2)
            if end == -1:
                out.append(code[index:])
                break
            out.append(" ")
            index = end + 2
        elif pair == '#"':
            text, end = _m_quoted_content(code, index + 2)
            if end == -1:
                out.append(code[index:])
                break
            if text not in slots:
                slots[text] = len(quoted)
                quoted.append(text)
            out.append(f"\x00{slots[text]}\x00")
            index = end
        elif code[index] == '"':
            end = _m_string_end(code, index + 1)
            if end == -1:
                out.append(code[index:])
                break
            out.append('""')
            index = end
        else:
            out.append(code[index])
            index += 1
    return "".join(out), quoted


def _dax_code(expr: str) -> str:
    """Blank DAX strings/comments; single-quoted spans stay verbatim.

    F13: qualified 'Table'[Name] extraction runs on this, so a
    qualified-looking token inside "..." or a comment adds no edge
    while genuine quoted identifiers survive for matching. The scan
    mirrors _dax_clean exactly (including naive single-quote spans
    so comment markers inside them are not misread); only the
    single-quote emission differs (verbatim instead of blanked).
    """
    out: list[str] = []
    index, size = 0, len(expr)
    while index < size:
        pair = expr[index:index + 2]
        if pair in ("//", "--"):
            end = expr.find("\n", index)
            if end == -1:
                break
            out.append(" ")
            index = end
        elif pair == "/*":
            end = expr.find("*/", index + 2)
            if end == -1:
                out.append(expr[index:])
                break
            out.append(" ")
            index = end + 2
        elif expr[index] == '"':
            end = _m_string_end(expr, index + 1)
            if end == -1:
                out.append(expr[index:])
                break
            out.append('""')
            index = end
        elif expr[index] == "'":
            end = index + 1
            while end < size and expr[end] != "'":
                end += 1
            out.append(expr[index:end + 1] if end < size else expr[index:])
            index = end + 1 if end < size else size
        else:
            out.append(expr[index])
            index += 1
    return "".join(out)


def _dax_clean(expr: str) -> str:
    """Blank DAX strings and comments so only real references remain.

    Handles "..." strings with "" escapes, // and -- line comments, and
    /* */ block comments. Unterminated constructs stay verbatim (fail
    closed: more edges, never fewer).
    """
    out: list[str] = []
    index, size = 0, len(expr)
    while index < size:
        pair = expr[index:index + 2]
        if pair in ("//", "--"):
            end = expr.find("\n", index)
            if end == -1:
                break
            out.append(" ")
            index = end
        elif pair == "/*":
            end = expr.find("*/", index + 2)
            if end == -1:
                out.append(expr[index:])
                break
            out.append(" ")
            index = end + 2
        elif expr[index] == '"':
            end = _m_string_end(expr, index + 1)
            if end == -1:
                out.append(expr[index:])
                break
            out.append('""')
            index = end
        elif expr[index] == "'":
            end = index + 1
            while end < size and expr[end] != "'":
                end += 1
            out.append("''" if end < size else expr[index:])
            index = end + 1 if end < size else size
        else:
            out.append(expr[index])
            index += 1
    return "".join(out)


def _restore(name: str, quoted: list[str]) -> str:
    match = _M_PLACEHOLDER.fullmatch(name)
    if match:
        index = int(match.group(1))
        if index < len(quoted):
            return quoted[index]
    return name


def _whole_word(name: str, code: str) -> bool:
    return re.search(r"(?<![\w#\.])" + re.escape(name) + r"(?![\w\.])",
                     code) is not None


def find_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """Depth-first cycle detection; each cycle repeats its start node."""
    visiting: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        visiting.add(node)
        stack.append(node)
        for dep in sorted(edges.get(node, ())):
            if dep in visiting:
                cycles.append(stack[stack.index(dep):] + [dep])
            elif dep not in done:
                visit(dep)
        stack.pop()
        visiting.discard(node)
        done.add(node)

    for node in sorted(edges):
        if node not in done:
            visit(node)
    seen: set[frozenset[str]] = set()
    unique = []
    for cycle in cycles:
        key = frozenset(cycle)
        if key not in seen:
            seen.add(key)
            unique.append(cycle)
    return unique


def _read_table_texts(model_dir: str) -> tuple[dict[str, str], list[str]]:
    """Read every tables/*.tmdl; return (path->text, unreadable paths)."""
    texts: dict[str, str] = {}
    skipped: list[str] = []
    pattern = os.path.join(model_dir, "tables", "*.tmdl")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                texts[path] = handle.read()
        except (OSError, ValueError):
            skipped.append(path)
    return texts, skipped


def dax_objects(model_dir: str) -> dict[tuple[str, str, str], str]:
    """Map ``(kind, table, name)`` to full DAX source.

    Nodes stay tuples through edge detection so dotted table or measure
    names can never be mis-split; ``check_model`` renders display labels.
    Extraction is shared with the binding checker (multiline, calculated
    columns, quoted identifiers); unreadable files are skipped here and
    reported by :func:`check_model` coverage.
    """
    objects: dict[tuple[str, str, str], str] = {}
    texts, _ = _read_table_texts(model_dir)
    for path in sorted(texts):
        extracted = extract_objects(texts[path])
        for table, content in extracted["tables"].items():
            for name, expr in content["measures"].items():
                objects[("measure", table, name)] = expr
            for name, expr in content["columns"].items():
                if expr:
                    objects[("column", table, name)] = expr
    return objects


def dax_edges(
        objects: dict[tuple[str, str, str], str]
) -> dict[tuple[str, str, str], set[tuple[str, str, str]]]:
    """Reference edges from qualified and bare ``[Name]`` uses.

    ``'Table'[Name]`` (or bare ``Table[Name]``) resolves exactly, so a
    qualifier can never silently redirect to a same-table lookalike.
    Bare ``[Name]`` prefers the same table, then the first parsed table
    (documented approximation); nothing is silently dropped. Matching is
    case-insensitive like DAX; node ids keep exact case. Strings and
    comments are blanked first so prose adds no edges.
    """
    by_table: dict[tuple[str, str], tuple[str, str, str]] = {}
    for node in objects:
        _kind, table, name = node
        by_table[(table.casefold(), name.casefold())] = node
    edges = {node: set() for node in objects}
    for node, expr in objects.items():
        _kind, table, _name = node
        code = _dax_code(expr)
        remaining = code
        for match in _QUALIFIED.finditer(code):
            qualifier = match.group(1) or match.group(3) or ""
            if match.group(1):
                qualifier = qualifier.replace("''", "'")
            key = (qualifier.casefold(), (match.group(2) or match.group(4)).casefold())
            if key in by_table:
                edges[node].add(by_table[key])
            remaining = remaining.replace(match.group(0), " ", 1)
        clean = _dax_clean(remaining)
        for ref in set(_BARE_REF.findall(clean)):
            key = (table.casefold(), ref.casefold())
            if key in by_table:
                edges[node].add(by_table[key])
            else:
                for (other_table, other_name), found in by_table.items():
                    if other_name == ref.casefold():
                        edges[node].add(found)
                        break
    return edges


def m_queries(model_dir: str) -> dict[str, str]:
    """Map query name to M code (shared expressions + m partitions)."""
    queries: dict[str, str] = {}
    try:
        with open(os.path.join(model_dir, "expressions.tmdl"),
                  encoding="utf-8-sig") as handle:
            shared = handle.read()
    except (OSError, ValueError):
        shared = ""
    for match in _EXPRESSION.finditer(shared):
        name = match.group(2) or match.group(3)
        body = re.sub(r"^\tannotation.*$", "", match.group(4),
                      flags=re.MULTILINE)
        queries[name] = body
    texts, _ = _read_table_texts(model_dir)
    for path in sorted(texts):
        text = texts[path]
        table = _table_name(text)
        if table is None:
            continue
        for match in _PARTITION_M.finditer(text):
            name = match.group(2) or match.group(3)
            queries[f"{table}|{name}"] = match.group(4)
    return queries


def _mask_binding_lhs(text: str, bound: set[str]) -> str:
    """Blank ``NAME =`` definitions so they never read as references.

    Right-hand occurrences (``D = B``) are untouched and resolve
    against the scope chain like any other reference.
    """
    masked = text
    for candidate in sorted(bound, key=len, reverse=True):
        masked = re.sub(r"(?<![\w#.])" + re.escape(candidate) + r"\s*=",
                        lambda match: " " * len(match.group(0)), masked)
    return masked


def _split_let_body(body: str, query: str) -> tuple[str, str]:
    """Split a nested-let body from its enclosing tail (S04).

    The body runs to the first depth-zero ``,``/``)``/``]``/``;`` or
    end of text; the tail belongs to an ancestor scope. Depth that
    never resolves is explicitly unsupported (ModelingError)
    instead of a guessed attribution.
    """
    depth = 0
    for pos, char in enumerate(body):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return body[:pos], body[pos:]
            depth -= 1
        elif char in ",;" and depth == 0:
            return body[:pos], body[pos:]
    if depth != 0:
        raise ModelingError(
            f"unbalanced brackets in nested let body of query {query!r}: "
            "unsupported by static scope analysis")
    return body, ""


def _region_refs(text: str, bare: str, quoted: list[str]) -> bool:
    """Whether a scope region references a query (word or quoted id)."""
    if _whole_word(bare, text):
        return True
    matches = [match.group(0) for match in _M_PLACEHOLDER.finditer(text)]
    return any(_restore(placeholder, quoted) == bare
               for placeholder in matches)


def _raise_on_middle_refs(query: str, declared: str, body: str, rest: str,
                           extra: set[str], ambiguous: set[str],
                           quoted: list[str]) -> None:
    """Block when a middle-scope name sits in an undelimitable region.

    T03: with the middle nested scope possibly still open, a
    reference to one of its bindings past the middle ``in`` is
    inner if the middle body reaches this far and outer if it
    ended. Either attribution may be wrong, so any occurrence
    raises ModelingError instead of resolving. Names bound in
    this segment's own rest (``extra``) are certain and excluded,
    as are deeper-scope and ancestor names.
    """
    masked_rest = _mask_binding_lhs(rest, extra)
    for candidate in sorted(ambiguous):
        if (_region_refs(declared, candidate, quoted)
                or _region_refs(body, candidate, quoted)
                or _region_refs(masked_rest, candidate, quoted)):
            raise ModelingError(
                f"nested let scope end cannot be delimited in query "
                f"{query!r}: reference to {candidate!r} may be inner "
                f"or outer")


def _raise_scope_chain(query: str) -> None:
    """Block an ``in``-chain past the middle scope end (T03).

    An ``in`` after the middle scope's own ``in`` opens an
    ancestor scope whose end is undelimitable here, so resolving
    would guess. Raise instead; the gate blocks these shapes too.
    """
    raise ModelingError(
        f"nested let scope chain beyond supported analysis in query "
        f"{query!r}: `in` past the middle scope end is unsupported "
        f"by static scope analysis")


def _mid_rest_regions(query: str, rest: str, extra: set[str],
                      scope_names: set[str], ancestors: set[str],
                      quoted: list[str],
                      regions: list[tuple[str, set[str]]]) -> bool:
    """Attribute the middle-``in`` rest across the scope end.

    T03: this rest holds the middle nested scope's ``in``. Text
    before it is binding remainder (inner, masked with the middle
    set); the ``in``-body runs to the first depth-zero delimiter
    (proven inner, masked); anything after is outer and masks
    ancestors only, unmasked (a tail ``NAME =`` is an equality
    reference, never a binding). A further ``in`` in the tail
    opens an ancestor scope: undelimitable, so it raises.
    Returns True when a scope end delimited (the middle scope
    provably closed).
    """
    found = _IN.search(rest)
    if found is None:  # unreachable: caller only routes `in` rests
        regions.append((_mask_binding_lhs(rest, extra),
                        scope_names | ancestors))
        return False
    inner = scope_names | ancestors
    regions.append((_mask_binding_lhs(rest[:found.start()], extra), inner))
    inner_part, tail = _split_let_body(rest[found.end():], query)
    regions.append((inner_part, inner))
    if _IN.search(tail) is not None:
        _raise_scope_chain(query)
    regions.append((tail, ancestors))
    return tail != ""


def m_edges(queries: dict[str, str]) -> dict[str, set[str]]:
    """Query-reference edges; literals/comments blanked, #"ids" matched.

    Lexical scope resolves per region. Names bound by a query's own
    leading ``let`` are local throughout it (``let Q = 1 in Q`` is
    not a Q->Q cycle). A nested ``let`` binds its names only inside
    its own body: outer references to a shared query name stay
    global edges, so ``A = B + (let B = 1 in B)`` with ``B = A`` is
    an A<->B cycle. Binding left-hand sides are definitions, never
    references; same-scope binding expressions resolve against the
    scope's bindings. Text after a nested body belongs to an
    ancestor scope, so root bindings after a nested let
    (``, B = 1 in B``) still complete the root scope instead of
    reading as global references. One level of nesting inside a
    binding expression (two levels total) resolves only with
    delimiter proof: M lets are order-independent, so the middle
    scope's bindings (fragment plus every later rest's pre-``in``
    pairs) mask everywhere inside the middle span, while the rest
    holding the middle ``in`` re-splits into proven-inner body
    and outer tail. Deeper nesting, truncated shapes,
    middle-scope names past an undelimited scope end, and
    ``in``-chains past the middle scope end raise ModelingError
    instead of mis-resolving.
    """
    edges: dict[str, set[str]] = {name: set() for name in queries}
    for name, code in queries.items():
        clean, quoted = _m_clean(code)
        parts = _LET.split(clean)
        leading = not parts[0].strip()
        if leading:
            top = (_top_bindings(_let_scope(parts[1]))
                   if len(parts) > 1 else [])
            ancestors = {_restore(binding, quoted) for binding, _ in top}
            nested = parts[2:]
            regions: list[tuple[str, set[str]]] = []
        else:
            ancestors = set()
            nested = parts[1:]
            regions = [(parts[0], set())]
        # T03: a nested fragment (split piece with no `in`) is a scope
        # broken open by a deeper let. Leading queries tolerate none
        # (root bindings split once already); non-leading queries
        # tolerate exactly one (their single nested scope). Anything
        # deeper cannot be delimited: block, never mis-resolve.
        frag_at = [index for index, segment in enumerate(nested)
                   if _IN.search(segment) is None]
        if (leading and frag_at) or len(frag_at) > 1:
            raise ModelingError(
                f"nested let beyond supported depth in query {name!r}: "
                "unsupported by static scope analysis")
        # Precompute each segment's bounds and body/rest split (one
        # split per segment; unbalanced bodies raise here as before).
        # Rest tails belong to an ancestor scope: their bindings
        # complete that scope instead of vanishing.
        infos: list[tuple[set[str], str, str, set[str]]] = []
        for segment in nested:
            has_in = _IN.search(segment)
            if has_in is None:
                pairs = _top_bindings(segment)
                infos.append(
                    ({_restore(binding, quoted) for binding, _ in pairs},
                     segment, "", set()))
                continue
            pairs = _top_bindings(segment[:has_in.start()])
            bound = {_restore(binding, quoted) for binding, _ in pairs}
            body, rest = _split_let_body(segment[has_in.end():], name)
            rest_pairs = _top_bindings(_let_scope(rest))
            extra = {_restore(binding, quoted)
                     for binding, _ in rest_pairs}
            infos.append((bound, body, rest, extra))
        if leading:
            for _bound, _body, _rest, extra in infos:
                ancestors |= extra
        # Non-leading single nested scope: M lets are
        # order-independent, so the middle scope's bindings mask
        # everywhere inside the middle span (fragment, deeper
        # regions, pre-`in` remainders, proven inner body). The
        # middle set unions the fragment with every later rest's
        # pre-`in` pairs; only text past the delimited middle scope
        # end resolves outward, and anything undelimitable raises.
        scope_names: set[str] = set()
        first_frag = frag_at[0] if frag_at else None
        if not leading and first_frag is not None:
            scope_names |= infos[first_frag][0]
            for pos in range(first_frag + 1, len(infos)):
                if _IN.search(nested[pos]) is not None:
                    scope_names |= infos[pos][3]
        # Locate the middle `in`: first `in` past the fragment,
        # bodies before rests per segment; a later `in` opens an
        # ancestor scope. Absent entirely, the shape is truncated.
        mid_at: tuple[int, bool] | None = None
        if not leading and first_frag is not None:
            for pos in range(first_frag + 1, len(infos)):
                if _IN.search(nested[pos]) is None:
                    continue
                _seg_bound, _seg_body, _seg_rest, _seg_extra = infos[pos]
                if _IN.search(_seg_body) is not None:
                    mid_at = (pos, True)
                    break
                if _IN.search(_seg_rest) is not None:
                    mid_at = (pos, False)
                    break
        middle_closed = False
        for index, segment in enumerate(nested):
            bound, body, rest, extra = infos[index]
            has_in = _IN.search(segment)
            if has_in is None:
                # let-fragment from a nested let inside a binding
                # expression: definitions mask, and same-middle-scope
                # references are inner in both directions (M lets
                # are order-independent, matching within_let_cycles).
                # Only names bound nowhere in range resolve outward.
                full = bound | scope_names | ancestors
                regions.append((_mask_binding_lhs(segment, full), full))
                continue
            declared = _mask_binding_lhs(segment[:has_in.start()], bound)
            shadowed = (not leading and first_frag is not None
                        and index > first_frag)
            inner = bound | ancestors
            if shadowed and (mid_at is None or index <= mid_at[0]):
                inner |= scope_names
            regions.append((declared, inner))
            regions.append((body, inner))
            if shadowed and (mid_at is None or (
                    mid_at is not None and index > mid_at[0]
                    and not middle_closed)):
                _raise_on_middle_refs(
                    name, declared, body, rest, extra,
                    scope_names - extra - bound - ancestors, quoted)
            if shadowed and mid_at is not None and index == mid_at[0]:
                if mid_at[1]:
                    # Middle `in` swallowed in the body: the body is
                    # deeper-body plus middle-body-start (masked
                    # above); a non-empty rest is post-body outer.
                    if rest == "":
                        middle_closed = False
                    elif _IN.search(rest) is not None:
                        _raise_scope_chain(query=name)
                    else:
                        regions.append((rest, ancestors))
                        middle_closed = True
                else:
                    middle_closed = _mid_rest_regions(
                        name, rest, extra, scope_names, ancestors,
                        quoted, regions)
            elif (shadowed and mid_at is not None
                    and index > mid_at[0] and middle_closed):
                if _IN.search(rest) is not None:
                    _raise_scope_chain(query=name)
                regions.append((_mask_binding_lhs(rest, extra),
                                ancestors | extra))
            else:
                mask = ancestors | extra
                if shadowed:
                    mask |= scope_names
                regions.append((_mask_binding_lhs(rest, extra), mask))
        if leading:
            top_text = parts[1] if len(parts) > 1 else ""
            regions.append((_mask_binding_lhs(top_text, ancestors),
                            set(ancestors)))
        for candidate in queries:
            bare = candidate.split("|")[-1]
            if leading and bare in ancestors:
                continue
            for text, bound in regions:
                if bare in bound:
                    continue
                if _region_refs(text, bare, quoted):
                    edges[name].add(candidate)
                    break
    return edges


def _let_scope(segment: str) -> str:
    """Top-level let scope of one split segment (up to its ``in``)."""
    has_in = _IN.search(segment)
    return segment[:has_in.start()] if has_in else segment


class ModelingError(ValueError):
    """Static model analysis hit an explicitly unsupported construct."""


def _top_bindings(scope: str) -> list[tuple[str, str]]:
    """Split cleaned let scope into top-level (name, expr) pairs.

    Splits only depth-zero commas so single-line lets, records, and
    calls segment correctly. :func:`m_edges` attributes each pair to
    its own scope instead of resolving through this flat view.
    """
    segments: list[str] = []
    depth = 0
    start = 0
    for pos, char in enumerate(scope):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            segments.append(scope[start:pos])
            start = pos + 1
    segments.append(scope[start:])
    pairs = []
    for segment in segments:
        match = re.match(r"\s*(\x00\d+\x00|[A-Za-z_][\w\.]*)\s*=",
                         segment)
        if match:
            pairs.append((match.group(1), segment[match.end():]))
    return pairs


def within_let_cycles(code: str) -> list[list[str]]:
    """Cycles between bindings inside a query's ``let`` blocks.

    Operates on comment/string-blanked code so ``in`` inside literals
    cannot truncate scope; #"quoted binding names" round-trip through
    placeholders and are restored in reported cycles. A nested ``let``
    inside a scope's own bindings hides the bindings after it, so it
    raises ModelingError (blocked) instead of a narrowed verdict.
    """
    clean, quoted = _m_clean(code)
    segments = _LET.split(clean)[1:]
    for segment in segments[:-1]:
        if _IN.search(segment) is None:
            # T03: a nested let inside this scope's bindings hides the
            # bindings after it (`, b = a in a` never parses): the
            # scope cannot be delimited, so block instead of reporting
            # a narrowed, possibly acyclic graph.
            raise ModelingError(
                "nested let inside a let binding hides later bindings: "
                "unsupported by static scope analysis")
    found: list[list[str]] = []
    for segment in segments:
        has_in = _IN.search(segment)
        scope = segment[:has_in.start()] if has_in else segment
        pairs = _top_bindings(scope)
        if not pairs:
            continue
        names = {name for name, _ in pairs}
        edges: dict[str, set[str]] = {name: set() for name in names}
        for name, expr in pairs:
            for candidate in names:
                if _whole_word(candidate, expr):
                    edges[name].add(candidate)
        for cycle in find_cycles(edges):
            found.append([_restore(node, quoted) for node in cycle])
    return found


def _tables_parsed(model_dir: str) -> int:
    """Count table files with a readable table declaration."""
    count = 0
    texts, _ = _read_table_texts(model_dir)
    for path in sorted(texts):
        if _table_name(texts[path]) is not None:
            count += 1
    return count


def _coverage(model_dir: str) -> dict:
    """Report which model files parsed; skipped files block the gate.

    TMDL extractor issues (orphans, unterminated spans, unclosed
    backticks, empty names) also break completeness: a narrowed graph
    must block instead of passing clean.
    """
    texts, skipped = _read_table_texts(model_dir)
    unparsed = [path for path in sorted(texts)
                if _table_name(texts[path]) is None]
    extract_issues: list[dict] = []
    for path in sorted(texts):
        for issue in extract_objects(texts[path])["issues"]:
            extract_issues.append({"part": path, **issue})
    shared = os.path.join(model_dir, "expressions.tmdl")
    shared_text = ""
    if os.path.isfile(shared):
        try:
            with open(shared, encoding="utf-8-sig") as handle:
                shared_text = handle.read()
        except (OSError, ValueError):
            skipped = [*skipped, shared]
            shared_text = ""
        for issue in extract_objects(shared_text)["issues"]:
            extract_issues.append({"part": "expressions.tmdl", **issue})
    if shared_text:
        # S05: every declared shared expression must be extracted;
        # dropped declarations block instead of passing narrowed.
        declared = {(match.group(2) or match.group(3))
                    for match in _EXPRESSION_ANY.finditer(shared_text)}
        extracted = {(match.group(2) or match.group(3))
                     for match in _EXPRESSION.finditer(shared_text)}
        missing = sorted(declared - extracted)
        if missing:
            extract_issues.append({"part": "expressions.tmdl",
                                   "rule": "unextracted_expression",
                                   "names": missing})
    for path in sorted(texts):
        # S05: same accounting for m partitions; non-m partition
        # kinds are unsupported for cycle purposes and block.
        declared = {(match.group(2) or match.group(3))
                    for match in _PARTITION_ANY.finditer(texts[path])}
        extracted = {(match.group(2) or match.group(3))
                     for match in _PARTITION_M.finditer(texts[path])}
        missing = sorted(declared - extracted)
        if missing:
            extract_issues.append({"part": path,
                                   "rule": "unextracted_partition",
                                   "names": missing})
    return {"parsed": sorted(texts), "skipped": sorted(skipped),
            "unparsed": sorted(unparsed),
            "extract_issues": extract_issues,
            "complete": not skipped and not unparsed and not extract_issues}


def check_model(model_dir: str) -> dict:
    """Run the static gate; raises OSError when the folder is unreadable.

    ``tables``/``dax_objects``/``m_queries`` count what was actually
    parsed: an empty folder reports ``acyclic: true`` with zero counts,
    which callers must read as "nothing to check", not as a clean bill.
    Any present-but-unreadable or table-less file raises ``OSError`` so
    partial parses block instead of passing narrowed.
    """
    if not os.path.isdir(model_dir):
        raise OSError(f"model folder not found: {model_dir}")
    coverage = _coverage(model_dir)
    if not coverage["complete"]:
        raise OSError("model parse coverage incomplete: "
                      f"skipped={coverage['skipped']} "
                      f"unparsed={coverage['unparsed']} "
                      f"extract_issues={coverage['extract_issues']}")
    tables = _tables_parsed(model_dir)
    dax = dax_objects(model_dir)
    queries = m_queries(model_dir)
    try:
        dax_loops = [[f"{kind}:{table}.{name}" for kind, table, name in cycle]
                     for cycle in find_cycles(dax_edges(dax))]
        m_loops = find_cycles(m_edges(queries))
        let_loops = []
        for name, code in sorted(queries.items()):
            for cycle in within_let_cycles(code):
                let_loops.append({"query": name, "cycle": cycle})
    except RecursionError as exc:
        raise OSError("Reference graph too deep to analyze") from exc
    return {"model_dir": model_dir,
            "tables": tables,
            "dax_objects": len(dax),
            "m_queries": len(queries),
            "dax_cycles": dax_loops,
            "m_cycles": m_loops,
            "let_cycles": let_loops,
            "acyclic": not (dax_loops or m_loops or let_loops),
            "coverage": coverage}
