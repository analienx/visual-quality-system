"""Modeling MCP port: primary read-only model/readiness/scoped DAX interface.

No new ADOMD requirement: all live-model access goes through the
Microsoft powerbi-modeling-mcp stdio server (optional dependency —
absent launcher blocks live paths, never offline ones). Every query
binds its scope (model identity, roles, filters, period, source) into
the returned context so later lanes can prove — or fail to prove —
that two answers share a scope. Scope *equality* alone never proves
answer preservation (GOAL 14, repair lane): answers compare by content.

Readiness separates steady refresh from first-open/loading instability
by querying twice: identical row evidence means repeatable; drift or
empty means unpopulated. Roles inject via MCP impersonation (real);
filters/period bind as recorded scope (compared, not injected).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class ModelingError(OSError):
    """Live-model access failed; capture maps this to blocked uniformly."""


@dataclass(frozen=True)
class ModelingScope:
    """Bound scope for a readiness probe or scoped query (all optional)."""

    model: str | None = None
    roles: tuple[str, ...] = ()
    filters: Any = None
    period: str | None = None
    source_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        doc = asdict(self)
        doc["roles"] = list(self.roles)
        return doc


class ModelingPort(Protocol):
    """Injectable live-model surface; fakes implement this in tests."""

    def connect(self) -> dict[str, Any]:
        """Bind one local model; raise ModelingError when ambiguous/absent."""
        ...  # pragma: no cover - protocol

    def readiness(self, scope: ModelingScope) -> dict[str, Any]:
        """Prove the bound scope is populated and repeatable."""
        ...  # pragma: no cover - protocol

    def query_scoped(self, dax: str, scope: ModelingScope,
                     max_rows: int = 100) -> dict[str, Any]:
        """Run DAX with bound scope; answers carry their context echo."""
        ...  # pragma: no cover - protocol

    def close(self) -> None:
        """Release the server process, if any."""
        ...  # pragma: no cover - protocol


_request_id_lock = threading.Lock()


def _request_id() -> str:
    with _request_id_lock:
        _request_id.counter += 1
        return f"vqs-{_request_id.counter}"


_request_id.counter = 0


class StdioModelingClient:
    """JSON-RPC stdio client for powerbi-modeling-mcp (lazy spawn)."""

    def __init__(self, command: tuple[str, ...] | list[str] | None = None,
                 timeout: int = 60) -> None:
        self._command = list(command) if command else ["powerbi-modeling-mcp"]
        self._timeout = timeout
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._model: str | None = None

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        binary = self._command[0]
        if "/" not in binary and "\\" not in binary and shutil.which(binary) is None:
            raise ModelingError(f"modeling launcher not on PATH: {binary}")
        try:
            self._process = subprocess.Popen(
                self._command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1)
        except OSError as exc:
            raise ModelingError(f"cannot start modeling server: {exc}") from exc
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        return self._process

    def _call(self, tool: str, request: dict[str, Any]) -> Any:
        """One tools/call round-trip; parsed result payload or ModelingError."""
        with self._lock:
            process = self._ensure_process()
            assert process.stdin is not None and process.stdout is not None
            rid = _request_id()
            message = json.dumps({"jsonrpc": "2.0", "id": rid,
                                  "method": "tools/call",
                                  "params": {"name": tool,
                                             "arguments": {"request": request}}})
            try:
                process.stdin.write(message + "\n")
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise ModelingError(f"modeling server write failed: {exc}") from exc
            line = self._read_line(process)
            try:
                response = json.loads(line)
            except ValueError as exc:
                raise ModelingError(
                    f"modeling server is not JSON: {line[:200]}") from exc
            if not isinstance(response, dict) or response.get("id") != rid:
                raise ModelingError("modeling server mismatched response id")
            if "error" in response:
                detail = response["error"]
                raise ModelingError(f"modeling {tool} error: {detail}")
            return self._payload(response.get("result"), tool)

    def _read_line(self, process: subprocess.Popen[str]) -> str:
        assert process.stdout is not None
        box: dict[str, Any] = {}
        worker = threading.Thread(target=self._read_target,
                                  args=(process.stdout, box), daemon=True)
        worker.start()
        worker.join(self._timeout)
        if worker.is_alive() or "error" in box:
            self._kill()
            raise ModelingError("modeling server timed out or closed")
        line = box.get("line", "")
        if not line:
            self._kill()
            raise ModelingError("modeling server closed the stream")
        return line

    @staticmethod
    def _read_target(stream: Any, box: dict[str, Any]) -> None:
        try:
            box["line"] = stream.readline()
        except (OSError, ValueError) as exc:
            box["error"] = exc

    def _payload(self, result: Any, tool: str) -> Any:
        if not isinstance(result, dict):
            raise ModelingError(f"modeling {tool} returned no result object")
        content = result.get("content", [])
        if not isinstance(content, list) or not content:
            raise ModelingError(f"modeling {tool} returned no content")
        first = content[0] if isinstance(content[0], dict) else {}
        text = first.get("text", "")
        if not isinstance(text, str) or not text:
            raise ModelingError(f"modeling {tool} returned empty content")
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ModelingError(
                f"modeling {tool} returned non-JSON content: {text[:200]}"
            ) from exc

    def _kill(self) -> None:
        # Order matters: kill and reap first (this EOFs the pipes and
        # releases any thread blocked in readline), close handles after.
        # Closing a pipe with a pending blocking read hangs on Windows.
        process, self._process = self._process, None
        if process is None:
            return
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        for stream in (process.stdin, process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
                process.wait(timeout=5)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass

    def connect(self) -> dict[str, Any]:
        """Bind exactly one local model; ambiguous/absent raises."""
        payload = self._call("connection_operations",
                             {"operation": "ListLocalInstances"})
        if isinstance(payload, list):
            instances = payload
        elif isinstance(payload, dict):
            instances = payload.get("instances", [])
        else:
            raise ModelingError("ListLocalInstances returned no list")
        if not isinstance(instances, list):
            raise ModelingError("ListLocalInstances returned no list")
        if not instances:
            raise ModelingError("no local Desktop model instances found")
        if len(instances) > 1:
            names = ", ".join(str(i.get("server", i)) for i in instances
                              if isinstance(i, dict))
            raise ModelingError("several local instances; disambiguate. "
                                f"Found: {names}")
        instance = instances[0] if isinstance(instances[0], dict) else {}
        data_source = str(_first_key(instance, "server", "dataSource",
                                     "instance", "name"))
        catalog = str(_first_key(instance, "database", "initialCatalog",
                                 "catalog", "databaseName"))
        if not data_source or not catalog:
            raise ModelingError(
                "local instance lacks server/database identity")
        connected = self._call("connection_operations",
                               {"operation": "Connect",
                                "dataSource": data_source,
                                "initialCatalog": catalog})
        if isinstance(connected, dict) and connected.get("isError"):
            raise ModelingError(f"Connect failed: {connected}")
        self._model = f"{data_source}/{catalog}"
        return {"model": self._model, "server": data_source,
                "database": catalog}

    def _stats(self) -> dict[str, Any]:
        payload = self._call("model_operations", {"operation": "GetStats"})
        if not isinstance(payload, dict):
            raise ModelingError("GetStats returned no object")
        return payload

    def _execute(self, dax: str, scope: ModelingScope,
                 max_rows: int) -> dict[str, Any]:
        request: dict[str, Any] = {"operation": "Execute", "query": dax,
                                   "resultMode": "Inline", "maxRows": max_rows}
        if scope.roles:
            request["impersonation"] = {"roles": list(scope.roles)}
        payload = self._call("dax_query_operations", request)
        if not isinstance(payload, dict):
            raise ModelingError("Execute returned no object")
        return payload

    @staticmethod
    def _rows_of(payload: dict[str, Any]) -> list[Any]:
        rows = payload.get("rows", payload.get("data", []))
        return rows if isinstance(rows, list) else []

    def readiness(self, scope: ModelingScope) -> dict[str, Any]:
        """Prove populated + repeatable: stats plus a twice-run probe query.

        When GetStats names tables, the probe COUNTROWS the first table
        twice: equal counts above zero prove data, not just a live engine.
        Otherwise the constant probe only proves the engine answers
        repeatably (probe_table None says so honestly); rowcount is probe
        rows, data_rows the counted data rows or None.
        """
        if self._model is None:
            self.connect()
        stats = self._stats()
        count, names, shape = _table_inventory(stats)
        base: dict[str, Any] = {"method": "modeling-mcp:repeat-query",
                                "scope_echo": scope.as_dict(),
                                "probe_table": names[0] if names else None,
                                "tables_shape": shape}
        if count <= 0:
            return {"populated": False, **base,
                    "detail": "model reports no tables"}
        probe_table = names[0] if names else None
        if probe_table is None:
            probe = 'EVALUATE ROW("ok", 1)'
        else:
            quoted = probe_table.replace("'", "''")
            probe = f"EVALUATE ROW(\"n\", COUNTROWS('{quoted}'))"
        first = self._rows_of(self._execute(probe, scope, 10))
        second = self._rows_of(self._execute(probe, scope, 10))
        if first != second:
            return {"populated": False, **base,
                    "detail": "probe answers unstable across repeats"}
        data_rows: int | None = None
        if probe_table is None:
            if not first:
                return {"populated": False, **base,
                        "detail": "probe query returned no rows"}
        else:
            data_rows = _count_of(first)
            if data_rows is None:
                return {"populated": False, **base,
                        "detail": f"COUNTROWS probe on '{probe_table}' "
                                  "returned no number"}
            if data_rows <= 0:
                return {"populated": False, **base,
                        "detail": f"table '{probe_table}' has no rows"}
        row_text = json.dumps(first, sort_keys=True, ensure_ascii=False,
                              default=str)
        echo = scope.as_dict()
        echo["model"] = echo.get("model") or self._model
        return {"populated": True, **base, "scope_echo": echo,
                "rowcount": len(first), "data_rows": data_rows,
                "query_hash": hashlib.sha256(row_text.encode("utf-8")
                                             ).hexdigest()}

    def query_scoped(self, dax: str, scope: ModelingScope,
                     max_rows: int = 100) -> dict[str, Any]:
        """Run DAX under bound scope; the answer echoes its full context."""
        if not isinstance(dax, str) or not dax.strip():
            raise ModelingError("DAX text must be a nonempty string")
        if self._model is None:
            self.connect()
        payload = self._execute(dax, scope, max_rows)
        rows = self._rows_of(payload)
        context = scope.as_dict()
        context["model"] = context.get("model") or self._model
        context["query_sha256"] = hashlib.sha256(
            dax.encode("utf-8")).hexdigest()
        return {"rows": rows, "rowcount": len(rows), "context": context}


def _table_inventory(stats: dict[str, Any]) -> tuple[int, list[str], str]:
    """(table count, table names, observed shape) across GetStats shapes."""
    raw = stats.get("tables", stats.get("tableCount", 0))
    shape = type(raw).__name__
    names: list[str] = []
    if isinstance(raw, bool):
        count = 0
    elif isinstance(raw, int):
        count = max(raw, 0)
    elif isinstance(raw, list):
        count = len(raw)
        for entry in raw:
            if isinstance(entry, str) and entry:
                names.append(entry)
            elif (isinstance(entry, dict)
                    and isinstance(entry.get("name"), str)
                    and entry["name"]):
                names.append(entry["name"])
    elif (isinstance(raw, dict) and isinstance(raw.get("count"), int)
            and not isinstance(raw.get("count"), bool)):
        count = max(raw["count"], 0)
    else:
        count = 0
    if not names:
        declared = stats.get("tableNames", [])
        if isinstance(declared, list):
            names = [n for n in declared if isinstance(n, str) and n]
    return count, names, shape


def _count_of(rows: list[Any]) -> int | None:
    """The single number of a COUNTROWS probe answer, else None."""
    if len(rows) != 1 or not isinstance(rows[0], dict) or len(rows[0]) != 1:
        return None
    value = next(iter(rows[0].values()))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _first_key(mapping: dict[str, Any], *names: str) -> Any:
    """First present non-empty value across plausible response keys."""
    for name in names:
        value = mapping.get(name)
        if value:
            return value
    return ""


def scope_from_dict(data: Any) -> ModelingScope:
    """Build a scope from untrusted input; malformed fields become None."""
    if not isinstance(data, dict):
        return ModelingScope()
    roles = data.get("roles", ())
    if isinstance(roles, str):
        roles = (roles,)
    if not isinstance(roles, (list, tuple)):
        roles = ()
    roles = tuple(r for r in roles if isinstance(r, str) and r)
    period = data.get("period")
    model = data.get("model")
    source = data.get("source_sha256")
    return ModelingScope(
        model=model if isinstance(model, str) else None,
        roles=roles,
        filters=data.get("filters"),
        period=period if isinstance(period, str) else None,
        source_sha256=source if isinstance(source, str) else None)


def compare_scope(expected: ModelingScope,
                  actual: dict[str, Any]) -> list[str]:
    """Names of bound scope fields that differ (model/roles/filters/period).

    source_sha256 is deliberately NOT compared here: source binding is
    enforced by capture's pre/post source_digest equality check, while
    this compares live-model scope only.
    """
    mismatches = []
    if expected.model is not None and actual.get("model") != expected.model:
        mismatches.append("model")
    if expected.roles and list(expected.roles) != list(
            actual.get("roles", []) or []):
        mismatches.append("roles")
    if expected.filters is not None and actual.get("filters") != expected.filters:
        mismatches.append("filters")
    if expected.period is not None and actual.get("period") != expected.period:
        mismatches.append("period")
    return mismatches
