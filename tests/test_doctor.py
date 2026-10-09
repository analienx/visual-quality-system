"""Doctor tests: shape-only; presence values depend on the machine."""
import json

from vqs.cli import main as vqs_main
from vqs.doctor import report


def test_report_shape() -> None:
    data = report()
    assert data["status"] == "ok"
    checks = data["checks"]
    assert set(checks) == {"report_author", "desktop_bridge", "modeling_mcp",
                           "desktop_process", "installation"}
    for name in ("report_author", "desktop_bridge", "modeling_mcp"):
        assert checks[name]["status"] in ("present", "missing")
    assert checks["report_author"]["name"] == "powerbi-report-author"
    assert (checks["report_author"]["package"]
            == "@microsoft/powerbi-report-authoring-cli")
    install = checks["installation"]
    assert install["distribution"] == "visual-quality-system"
    assert install["import_root"].endswith("vqs")
    assert set(install["schemas"]) == {"config", "tool", "plan",
                                       "reviewer", "policy", "ledger",
                                       "contracts", "mcp_protocol"}
    assert isinstance(install["stale"], bool)


def test_doctor_command_exits_zero(capsys) -> None:
    assert vqs_main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
