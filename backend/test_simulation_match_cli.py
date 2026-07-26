import json
import subprocess
import sys

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
MATCH_ARGUMENTS = (
    "match",
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
REQUIRED_FIELDS = {
    "match_id",
    "seed",
    "bot_a",
    "bot_b",
    "starting_stack",
    "small_blind",
    "big_blind",
    "max_hands",
    "hands_played",
    "final_stack_a",
    "final_stack_b",
    "winner",
    "termination_reason",
    "bot_a_net_chips",
    "bot_b_net_chips",
    "showdowns",
    "fold_ended_hands",
    "illegal_actions",
    "fallback_diagnostics",
    "hand_summaries",
}


def cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "simulation.cli", *map(str, arguments)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_valid_match_exits_zero_and_prints_json():
    completed = cli(*MATCH_ARGUMENTS)
    assert completed.returncode == 0, completed.stderr
    assert isinstance(json.loads(completed.stdout), dict)


def test_cli_match_contains_required_fields():
    result = json.loads(cli(*MATCH_ARGUMENTS).stdout)
    assert REQUIRED_FIELDS <= result.keys()
    assert result["hand_summaries"]


def test_cli_match_is_deterministic_for_the_same_seed():
    first = json.loads(cli(*MATCH_ARGUMENTS).stdout)
    second = json.loads(cli(*MATCH_ARGUMENTS).stdout)
    first.pop("match_id")
    second.pop("match_id")
    assert first == second


def test_cli_accepts_case_normalized_bot_names():
    arguments = list(MATCH_ARGUMENTS)
    arguments[arguments.index("tight")] = "TIGHT"
    arguments[arguments.index("aggressive")] = "AgGrEsSiVe"
    completed = cli(*arguments)
    assert completed.returncode == 0, completed.stderr


def test_invalid_cli_bot_exits_nonzero_with_useful_error():
    completed = cli("match", "--bot-a", "unsupported")
    assert completed.returncode != 0
    assert "invalid choice" in completed.stderr.lower()


def test_invalid_cli_stack_exits_nonzero_with_useful_error():
    completed = cli("match", "--starting-stack", "0")
    assert completed.returncode != 0
    assert "starting_stack must be positive" in completed.stderr


def test_invalid_cli_blind_relationship_exits_nonzero():
    completed = cli(
        "match",
        "--small-blind",
        "101",
        "--big-blind",
        "100",
    )
    assert completed.returncode != 0
    assert "small_blind cannot exceed big_blind" in completed.stderr


def test_invalid_cli_hand_limit_exits_nonzero():
    completed = cli("match", "--max-hands", "10001")
    assert completed.returncode != 0
    assert "max_hands must be between" in completed.stderr


def test_existing_cli_list_bots_still_works():
    completed = cli("list-bots")
    assert completed.returncode == 0
    assert completed.stdout.splitlines() == [
        "random",
        "tight",
        "aggressive",
        "equity",
    ]


def test_existing_independent_cli_run_still_works():
    completed = cli(
        "run",
        "--bot-a",
        "random",
        "--bot-b",
        "tight",
        "--hands",
        "2",
        "--seed",
        "42",
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["hands_played"] == 2
    assert "match_id" not in result


def test_cli_and_api_produce_equivalent_match_results():
    cli_result = json.loads(cli(*MATCH_ARGUMENTS).stdout)
    api_result = client.post(
        "/api/matches/simulate",
        json={
            "bot_a": "tight",
            "bot_b": "aggressive",
            "starting_stack": 1000,
            "small_blind": 5,
            "big_blind": 10,
            "max_hands": 3,
            "seed": 42,
            "equity_iterations": 500,
        },
    ).json()
    cli_result.pop("match_id")
    api_result.pop("match_id")
    assert cli_result == api_result
