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
"""
from __future__ import annotations

import glob
import os
import re

_DAX_HEADER = re.compile(r"^\t(measure|column) ('([^']+)'|([^\s=]+)) = (.*)$")
_TABLE_QUOTED = re.compile(r"^table '(.+)'$", re.MULTILINE)
_TABLE_BARE = re.compile(r"^table (\S+)$", re.MULTILINE)
_EXPRESSION = re.compile(
    r"^expression\s+('([^']+)'|([^\s=]+))\s*=\s*(.*?)(?=^expression\s|\Z)",
    re.MULTILINE | re.DOTALL)
_PARTITION_M = re.compile(
    r"^\tpartition\s+('([^']+)'|([^\s=]+))\s*=\s*m\s*$(.*?)(?=^\t\S|\Z)",
    re.MULTILINE | re.DOTALL)
_STRING_LITERAL = re.compile(r'"(?:[^"]|"")*"')
_BINDING = re.compile(r"^\s*(#?\"[^\"]+\"|[A-Za-z_][\w\.]*)\s*=",
                       re.MULTILINE)
_BINDING_SPLIT = re.compile(r"^\s*(?:#?\"[^\"]+\"|[A-Za-z_][\w\.]*)\s*=",
                            re.MULTILINE)
_LET = re.compile(r"(?<![\w])let(?![\w])")
_IN = re.compile(r"(?<![\w])in(?![\w])")


def _table_name(text: str) -> str | None:
    match = _TABLE_QUOTED.search(text) or _TABLE_BARE.search(text)
    return match.group(1) if match else None


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


def dax_objects(model_dir: str) -> dict[str, str]:
    """Map ``kind:Table.Name`` to full DAX source for measures/columns."""
    objects: dict[str, str] = {}
    pattern = os.path.join(model_dir, "tables", "*.tmdl")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                text = handle.read()
        except (OSError, ValueError):
            continue
        table = _table_name(text)
        if table is None:
            continue
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            header = _DAX_HEADER.match(lines[index])
            if header is None:
                index += 1
                continue
            kind = header.group(1)
            name = header.group(3) or header.group(4)
            body = [header.group(5)]
            index += 1
            while (index < len(lines)
                   and not re.match(r"^\t\S", lines[index])):
                body.append(lines[index])
                index += 1
            objects[f"{kind}:{table}.{name}"] = "\n".join(body)
    return objects


def _split_node(node: str) -> tuple[str, str, str]:
    """Split kind:Table.Name; rsplit tolerates dotted table names."""
    kind, dotted = node.split(":", 1)
    table, name = dotted.rsplit(".", 1)
    return kind, table, name


def dax_edges(objects: dict[str, str]) -> dict[str, set[str]]:
    """Reference edges from ``[Name]`` uses; same-table names win.

    Matching is case-insensitive like DAX; node ids keep exact case.
    """
    by_table: dict[tuple[str, str], tuple[str, str, str]] = {}
    for node in objects:
        kind, table, name = _split_node(node)
        by_table[(table.casefold(), name.casefold())] = (kind, table, name)
    edges: dict[str, set[str]] = {node: set() for node in objects}
    for node, expr in objects.items():
        _, table, _ = _split_node(node)
        for ref in set(re.findall(r"\[([^\[\]]+)\]", expr)):
            key = (table.casefold(), ref.casefold())
            if key in by_table:
                kind, found_table, found_name = by_table[key]
                edges[node].add(f"{kind}:{found_table}.{found_name}")
            else:
                for (other_table, other_name), found in by_table.items():
                    if other_name == ref.casefold():
                        kind, found_table, found_name = found
                        edges[node].add(f"{kind}:{found_table}.{found_name}")
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
    pattern = os.path.join(model_dir, "tables", "*.tmdl")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                text = handle.read()
        except (OSError, ValueError):
            continue
        table = _table_name(text)
        if table is None:
            continue
        for match in _PARTITION_M.finditer(text):
            name = match.group(2) or match.group(3)
            queries[f"{table}|{name}"] = match.group(4)
    return queries


def m_edges(queries: dict[str, str]) -> dict[str, set[str]]:
    """Query-reference edges; string literals are blanked first."""
    edges: dict[str, set[str]] = {name: set() for name in queries}
    for name, code in queries.items():
        bare = _STRING_LITERAL.sub('""', code)
        for candidate in queries:
            if _whole_word(candidate.split("|")[-1], bare):
                edges[name].add(candidate)
    return edges


def within_let_cycles(code: str) -> list[list[str]]:
    """Cycles between bindings inside a query's ``let`` blocks."""
    found: list[list[str]] = []
    segments = _LET.split(code)
    for segment in segments[1:]:
        has_in = _IN.search(segment)
        scope = segment[:has_in.start()] if has_in else segment
        bindings = [match.group(1).strip('"').lstrip("#").strip('"')
                    for match in _BINDING.finditer(scope)]
        if not bindings:
            continue
        names = set(bindings)
        chunks = _BINDING_SPLIT.split(scope)
        edges: dict[str, set[str]] = {name: set() for name in names}
        for position, binding in enumerate(bindings):
            if position + 1 >= len(chunks):
                continue
            expr = _STRING_LITERAL.sub('""', chunks[position + 1])
            for candidate in names:
                if _whole_word(candidate, expr):
                    edges[binding].add(candidate)
        found.extend(find_cycles(edges))
    return found


def _tables_parsed(model_dir: str) -> int:
    """Count table files with a readable table declaration."""
    count = 0
    pattern = os.path.join(model_dir, "tables", "*.tmdl")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                text = handle.read()
        except (OSError, ValueError):
            continue
        if _table_name(text) is not None:
            count += 1
    return count


def check_model(model_dir: str) -> dict:
    """Run the static gate; raises OSError when the folder is unreadable.

    ``tables``/``dax_objects``/``m_queries`` count what was actually
    parsed: an empty folder reports ``acyclic: true`` with zero counts,
    which callers must read as "nothing to check", not as a clean bill.
    """
    if not os.path.isdir(model_dir):
        raise OSError(f"model folder not found: {model_dir}")
    tables = _tables_parsed(model_dir)
    dax = dax_objects(model_dir)
    queries = m_queries(model_dir)
    try:
        dax_loops = find_cycles(dax_edges(dax))
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
            "acyclic": not (dax_loops or m_loops or let_loops)}
