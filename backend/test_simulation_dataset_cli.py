import json
import subprocess
import sys

import pytest

from simulation.dataset import HIDDEN_FIELDS, SCHEMA_VERSION
from test_simulation_dataset_validation import valid_record


def cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "simulation.cli", *map(str, arguments)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_actual_cli_generates_and_validates_dataset(tmp_path):
    path = tmp_path / "valid.jsonl"
    generated = cli(
        "run",
        "--bot-a",
        "random",
        "--bot-b",
        "tight",
        "--hands",
        "5",
        "--seed",
        "42",
        "--dataset-output",
        path,
        "--overwrite",
    )
    assert generated.returncode == 0, generated.stderr
    summary = json.loads(generated.stdout)
    assert summary["hands_played"] == 5
    assert path.exists() and path.stat().st_size > 0

    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert records
    assert {record["schema_version"] for record in records} == {SCHEMA_VERSION}
    assert {record["simulation_id"] for record in records} == {
        summary["simulation_id"]
    }
    assert all(1 <= record["hand_number"] <= 5 for record in records)
    assert all(not HIDDEN_FIELDS & record.keys() for record in records)
    for hand_number in range(1, 6):
        indexes = [
            record["decision_index"]
            for record in records
            if record["hand_number"] == hand_number
        ]
        assert indexes == list(range(len(indexes)))

    validated = cli("validate-dataset", path)
    assert validated.returncode == 0, validated.stderr
    validation = json.loads(validated.stdout)
    assert validation["invalid_records"] == 0
    assert validation["records_checked"] == len(records)
    assert validation["hands_found"] == 5


@pytest.mark.parametrize(
    "content,reason",
    [
        ("{broken}\n", "Expecting"),
        ("\n", "blank JSONL record"),
        (
            json.dumps({**valid_record(), "schema_version": "1.0"}) + "\n",
            "unsupported schema_version",
        ),
        (
            json.dumps(
                {
                    **valid_record(),
                    "chosen_action": {"type": "check", "amount": None},
                    "chosen_target_to": None,
                    "action_classification": "free_check",
                }
            )
            + "\n",
            "absent from legal_actions",
        ),
    ],
    ids=["malformed-json", "blank-record", "unsupported-schema", "illegal-action"],
)
def test_validator_cli_returns_nonzero_with_line_and_reason(tmp_path, content, reason):
    path = tmp_path / "invalid.jsonl"
    path.write_text(content, encoding="utf-8")
    result = cli("validate-dataset", path)
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["invalid_records"] >= 1
    assert output["errors"][0]["line"] == 1
    assert reason in output["errors"][0]["reason"]


def test_validator_cli_never_reports_partial_success(tmp_path):
    path = tmp_path / "partial.jsonl"
    path.write_text(
        json.dumps(valid_record()) + "\n" + "{malformed}\n",
        encoding="utf-8",
    )
    result = cli("validate-dataset", path)
    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["records_checked"] == 2
    assert output["invalid_records"] == 1
