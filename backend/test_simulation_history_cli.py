import json
import subprocess
import sys


HAND_ARGUMENTS = (
    "history-hand",
    "--bot-a",
    "tight",
    "--bot-b",
    "aggressive",
    "--starting-stack-a",
    "1000",
    "--starting-stack-b",
    "1000",
    "--small-blind",
    "5",
    "--big-blind",
    "10",
    "--button-player",
    "a",
    "--seed",
    "42",
    "--equity-iterations",
    "500",
)
MATCH_ARGUMENTS = (
    "history-match",
    "--bot-a",
    "tight",
    "--bot-b",
    "aggressive",
    "--starting-stack",
    "1000",
    "--small-blind",
    "5",
    "--big-blind",
    "10",
    "--max-hands",
    "3",
    "--seed",
    "42",
    "--equity-iterations",
    "500",
)


def cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "simulation.cli", *map(str, arguments)],
        text=True,
        capture_output=True,
        check=False,
    )


def export_document(tmp_path, arguments, name):
    path = tmp_path / name
    completed = cli(*arguments, "--output", path)
    assert completed.returncode == 0, completed.stderr
    return path, json.loads(completed.stdout)


def test_history_hand_cli_exits_zero_and_prints_json():
    completed = cli(*HAND_ARGUMENTS)
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document["document_type"] == "hand_history"
    assert document["validation"]["valid"] is True


def test_history_match_cli_exits_zero_and_prints_every_history():
    completed = cli(*MATCH_ARGUMENTS)
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document["document_type"] == "match_history"
    assert document["history_count"] == document["match"]["hands_played"]
    assert len(document["histories"]) == document["history_count"]


def test_history_cli_is_deterministic():
    assert json.loads(cli(*HAND_ARGUMENTS).stdout) == json.loads(
        cli(*HAND_ARGUMENTS).stdout
    )


def test_output_file_is_utf8_json_and_matches_stdout(tmp_path):
    path, stdout_document = export_document(
        tmp_path, HAND_ARGUMENTS, "hand.json"
    )
    file_document = json.loads(path.read_text(encoding="utf-8"))
    assert file_document == stdout_document
    assert path.read_bytes().endswith(b"\n")


def test_existing_output_requires_overwrite_and_overwrite_succeeds(tmp_path):
    path, _ = export_document(tmp_path, HAND_ARGUMENTS, "existing.json")
    refused = cli(*HAND_ARGUMENTS, "--output", path)
    assert refused.returncode != 0
    assert "use --overwrite" in refused.stderr
    replaced = cli(*HAND_ARGUMENTS, "--output", path, "--overwrite")
    assert replaced.returncode == 0, replaced.stderr
    assert json.loads(path.read_text(encoding="utf-8"))["document_type"] == (
        "hand_history"
    )


def test_validator_accepts_valid_hand_document(tmp_path):
    path, _ = export_document(tmp_path, HAND_ARGUMENTS, "valid-hand.json")
    completed = cli("validate-history", path)
    result = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert result["valid"] is True
    assert result["document_type"] == "hand_history"
    assert result["histories_checked"] == result["valid_histories"] == 1
    assert result["invalid_histories"] == 0
    assert result["schema_versions_found"] == ["1.0"]


def test_validator_accepts_valid_match_document(tmp_path):
    path, document = export_document(
        tmp_path, MATCH_ARGUMENTS, "valid-match.json"
    )
    completed = cli("validate-history", path)
    result = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert result["valid"] is True
    assert result["document_type"] == "match_history"
    assert result["histories_checked"] == document["history_count"]
    assert result["valid_histories"] == document["history_count"]


def test_validator_rejects_malformed_json(tmp_path):
    path = tmp_path / "malformed.json"
    path.write_text("{broken", encoding="utf-8")
    completed = cli("validate-history", path)
    result = json.loads(completed.stdout)
    assert completed.returncode != 0
    assert result["valid"] is False
    assert "unable to read valid JSON" in str(result["errors"])


def test_validator_rejects_unsupported_schema(tmp_path):
    path, document = export_document(tmp_path, HAND_ARGUMENTS, "schema.json")
    document["history_schema_version"] = "9.0"
    document["history"]["history_schema_version"] = "9.0"
    path.write_text(json.dumps(document), encoding="utf-8")
    completed = cli("validate-history", path)
    result = json.loads(completed.stdout)
    assert completed.returncode != 0
    assert result["valid"] is False
    assert "unsupported history schema" in str(result["errors"])
    assert result["schema_versions_found"] == ["9.0"]


def test_validator_rejects_reordered_event_indexes(tmp_path):
    path, document = export_document(tmp_path, HAND_ARGUMENTS, "indexes.json")
    events = document["history"]["events"]
    events[1], events[2] = events[2], events[1]
    path.write_text(json.dumps(document), encoding="utf-8")
    completed = cli("validate-history", path)
    result = json.loads(completed.stdout)
    assert completed.returncode != 0
    assert "event indexes" in str(result["errors"])


def test_validator_rejects_broken_conservation_and_exits_nonzero(tmp_path):
    path, document = export_document(
        tmp_path, HAND_ARGUMENTS, "conservation.json"
    )
    document["history"]["events"][1]["stack_a_after"] += 1
    path.write_text(json.dumps(document), encoding="utf-8")
    completed = cli("validate-history", path)
    result = json.loads(completed.stdout)
    assert completed.returncode != 0
    assert result["invalid_histories"] == 1
    assert "chip conservation" in str(result["errors"])


def test_invalid_history_command_input_exits_nonzero():
    completed = cli("history-hand", "--starting-stack-a", "0")
    assert completed.returncode != 0
    assert "starting stacks must be positive" in completed.stderr


def test_exported_documents_contain_no_forbidden_keys(tmp_path):
    hand_path, _ = export_document(tmp_path, HAND_ARGUMENTS, "private-hand.json")
    match_path, _ = export_document(
        tmp_path, MATCH_ARGUMENTS, "private-match.json"
    )
    forbidden = {
        "deck",
        "deck_order",
        "remaining_deck",
        "remaining_cards",
        "burn_cards",
        "future_cards",
    }

    def scan(value):
        if isinstance(value, dict):
            assert not forbidden & value.keys()
            for child in value.values():
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(json.loads(hand_path.read_text(encoding="utf-8")))
    scan(json.loads(match_path.read_text(encoding="utf-8")))
