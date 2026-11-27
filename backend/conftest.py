import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: multi-second end-to-end tests (all run by default; deselect with -m \"not slow\")")
    config.addinivalue_line(
        "markers",
        "machine_exact: compares bit-exact numbers recorded on the owner's PC; other CPUs "
        "(for example AVX-512 CI runners) round differently, so CI runs these separately",
    )


@pytest.fixture(scope="session")
def adaptive_learning_reference(tmp_path_factory):
    backend = Path(__file__).parent
    reference = backend / "test_data" / "equiv_learning_phase_4h.json"
    expected = json.loads(reference.read_text(encoding="utf-8"))
    output = tmp_path_factory.mktemp("solver-learning") / "fingerprint.json"
    # BLAS accumulation changes slightly across thread layouts. Set the same
    # layout as the reference before NumPy loads to keep an exact comparison.
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
    subprocess.run(
        [sys.executable, "-m", "equiv_learning", str(output), str(expected["hands"])],
        cwd=backend, env=env, check=True, timeout=600,
    )
    return expected, json.loads(output.read_text(encoding="utf-8"))
