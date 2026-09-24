import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_mandatory_routing.py"


def run(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(ROOT / "formal" / fixture)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_complete_guidance_coordinator_ui_trace_passes() -> None:
    result = run("mandatory-routing.pass.json")
    assert result.returncode == 0, result.stderr
    assert "AWG-ROUTING-PASS" in result.stdout


def test_bypass_stale_partial_and_cross_ar_traces_fail_closed() -> None:
    for fixture in (
        "mandatory-routing.bypass.invalid.json",
        "mandatory-routing.stale.invalid.json",
        "mandatory-routing.partial.invalid.json",
        "mandatory-routing.cross-ar.invalid.json",
    ):
        result = run(fixture)
        assert result.returncode != 0, fixture
        assert "AWG-ROUTING-FAIL" in result.stderr, fixture


def test_contract_names_the_executable_evidence() -> None:
    contract = json.loads((ROOT / "formal" / "mandatory-routing.json").read_text())
    assert contract["checker"] == "tools/check_mandatory_routing.py"
    assert len(contract["negative_traces"]) == 4
