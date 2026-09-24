import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_multi_ar_batch.py"


def run(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECKER), str(ROOT / "formal" / fixture)], text=True, capture_output=True, check=False)


def test_complete_batch_round_trips_all_points_and_client_projections() -> None:
    result = run("multi-ar-batch.pass.json")
    assert result.returncode == 0, result.stderr
    assert "AWUI-BATCH-PASS" in result.stdout


def test_empty_duplicate_stale_and_partial_batches_fail_closed() -> None:
    for fixture in ("multi-ar-batch.empty.invalid.json", "multi-ar-batch.duplicate.invalid.json", "multi-ar-batch.stale.invalid.json", "multi-ar-batch.partial.invalid.json"):
        result = run(fixture)
        assert result.returncode != 0, fixture
        assert "AWUI-BATCH-FAIL" in result.stderr, fixture


def test_contract_names_checker_and_required_surfaces() -> None:
    contract = json.loads((ROOT / "formal" / "multi-ar-batch.json").read_text())
    assert contract["checker"] == "tools/check_multi_ar_batch.py"
    assert contract["required_projections"] == ["design", "workplan"]
    assert contract["required_clients"] == ["tui", "gui"]
