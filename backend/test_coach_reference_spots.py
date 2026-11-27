from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.slow
@pytest.mark.machine_exact
def test_heads_up_advice_matches_reference_spots():
    result = subprocess.run(
        [sys.executable, "-m", "coach.reference_spots"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
