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

_TABLE_QUOTED = re.compile(r"^table '(.+)'$", re.MULTILINE)
_TABLE_BARE = re.compile(r"^table (\S+)$", re.MULTILINE)
_EXPRESSION = re.compile(
    r"^expression\s+('([^']+)'|([^\s=]+))\s*=\s*(.*?)(?=^expression\s|\Z)",
    re.MULTILINE | re.DOTALL)
_PARTITION_M = re.compile(
    r"^\tpartition\s+('([^']+)'|([^\s=]+))\s*=\s*m\s*$(.*?)(?=^\t\S|\Z)",
    re.MULTILINE | re.DOTALL)
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
            quoted.append(text)
            out.append(f"\x00{len(quoted) - 1}\x00")
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


def m_edges(queries: dict[str, str]) -> dict[str, set[str]]:
    """Query-reference edges; literals/comments blanked, #"ids" matched."""
    edges: dict[str, set[str]] = {name: set() for name in queries}
    for name, code in queries.items():
        clean, quoted = _m_clean(code)
        for candidate in queries:
            bare = candidate.split("|")[-1]
            if _whole_word(bare, clean) or bare in quoted:
                edges[name].add(candidate)
    return edges


def _top_bindings(scope: str) -> list[tuple[str, str]]:
    """Split cleaned let scope into top-level (name, expr) pairs.

    Splits only depth-zero commas so single-line lets, records, and
    calls segment correctly. Nested ``let`` blocks share one namespace
    (documented over-approximation; extra edges fail closed).
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
    placeholders and are restored in reported cycles.
    """
    clean, quoted = _m_clean(code)
    found: list[list[str]] = []
    for segment in _LET.split(clean)[1:]:
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
    """Report which model files parsed; skipped files block the gate."""
    texts, skipped = _read_table_texts(model_dir)
    unparsed = [path for path in sorted(texts)
                if _table_name(texts[path]) is None]
    shared = os.path.join(model_dir, "expressions.tmdl")
    if os.path.isfile(shared):
        try:
            with open(shared, encoding="utf-8-sig") as handle:
                handle.read()
        except (OSError, ValueError):
            skipped = [*skipped, shared]
    return {"parsed": sorted(texts), "skipped": sorted(skipped),
            "unparsed": sorted(unparsed),
            "complete": not skipped and not unparsed}


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
                      f"unparsed={coverage['unparsed']}")
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
