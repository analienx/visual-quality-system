"""Current Microsoft Modeling MCP envelope and Desktop PID binding contracts."""
import pytest

from vqs.powerbi.modeling import (
    ModelingError,
    ModelingScope,
    StdioModelingClient,
)


def _client(target_pid=None, *, several=False):
    client = StdioModelingClient(target_pid=target_pid)
    local = [
        {"processId": 111, "port": 62819,
         "connectionString": "data source=localhost:62819",
         "parentProcessName": "PBIDesktop"},
    ]
    if several:
        local.append({"processId": 222, "port": 62820,
                      "connectionString": "data source=localhost:62820",
                      "parentProcessName": "PBIDesktop"})
    calls = []

    def vendor(tool, request):
        calls.append((tool, request))
        operation = request["operation"]
        if operation == "ListLocalInstances":
            return {"operation": operation, "message": "Found locals",
                    "data": local}
        if operation == "Connect":
            return {"operation": operation, "message": "connected",
                    "data": "PBIDesktop-TestModel-62819"}
        if operation == "GetStats":
            return {"operation": operation, "message": "statistics",
                    "data": {"TableCount": 2, "Tables": [
                        {"name": "Dim Customer", "columnCount": 4},
                        {"name": "Fact Sales", "columnCount": 5}]}}
        if operation == "Execute":
            return {"operation": operation, "message": "query executed",
                    "data": {"rowCount": 1, "rows": [
                        {"[n]": 18}]}}
        raise AssertionError(operation)

    client._call = vendor
    client._desktop_owner_pid = lambda instance: (
        555 if instance.get("processId") == 111 else 666)
    return client, calls


def test_vendor_current_shape_connects_and_proves_populated_data():
    client, calls = _client(target_pid=555, several=True)
    selected = client.connect()
    assert selected["enginePid"] == 111
    assert selected["desktopPid"] == 555
    assert "62819" in selected["model"]
    ready = client.readiness(ModelingScope())
    assert ready["populated"] is True
    assert ready["probe_table"] == "Dim Customer"
    assert ready["data_rows"] == 18
    answer = client.query_scoped('EVALUATE ROW("n", 18)', ModelingScope())
    assert answer["rows"] == [{"[n]": 18}]
    assert answer["context"]["model"] == selected["model"]
    assert sum(req["operation"] == "Execute" for _, req in calls) == 3


def test_target_pid_never_borrows_another_model():
    client, calls = _client(target_pid=999, several=True)
    with pytest.raises(ModelingError, match="PID 999 has no OS-bound"):
        client.connect()
    assert all(request["operation"] != "Connect" for _, request in calls)


def test_ambiguous_desktop_requires_exact_pid():
    client, calls = _client(several=True)
    with pytest.raises(ModelingError, match="pass an exact Desktop PID"):
        client.connect()
    assert all(request["operation"] != "Connect" for _, request in calls)


def test_vendor_failed_response_cannot_be_treated_as_success():
    client, _ = _client(target_pid=555)
    assert isinstance(client._vendor_data(
        {"operation": "GetStats", "data": {"TableCount": 1}}, "GetStats"), dict)
    with pytest.raises(ModelingError, match="Microsoft GetStats failed"):
        client._vendor_data({
            "operation": "GetStats", "success": False,
            "message": "not authorized", "data": {}}, "GetStats")


@pytest.mark.parametrize("value", [True, 0, -2, "71596"])
def test_target_pid_needs_positive_integer(value):
    with pytest.raises(ModelingError, match="target_pid"):
        StdioModelingClient(target_pid=value)


@pytest.mark.parametrize("connection,port", [
    ("data source=evil.example:62819", 62819),
    ("data source=localhost:62819", 63811),
    ("data source=localhost:99999", 99999),
])
def test_local_instance_discovery_never_redirects_mcp_connection(
        connection, port):
    client = StdioModelingClient(target_pid=555)
    requests = []

    def vendor(_tool, req):
        requests.append(req["operation"])
        assert req["operation"] == "ListLocalInstances"
        return {"operation": "ListLocalInstances", "data": [{
            "processId": 111, "port": port,
            "connectionString": connection}]}

    client._call = vendor
    client._desktop_owner_pid = lambda _instance: 555
    with pytest.raises(ModelingError, match="unsafe connection host|port disagrees"):
        client.connect()
    assert requests == ["ListLocalInstances"]
