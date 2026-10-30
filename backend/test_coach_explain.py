"""Coach explanations (EV, range, reason), opponent type labels, and the hand review."""
import pytest
from fastapi.testclient import TestClient

import main
from coach import explain
from coach.review import leaks, review
from coach.service import Spot, SpotAction, advise, log_hand, profile_for, profile_summary
from coach.store import HandStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "coach.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    return HandStore(path)


def spot(*actions, board=(), position="button", cards=("As", "Kd"), villain_cards=None):
    return Spot(hero_cards=list(cards), board=list(board), hero_position=position,
                actions=[SpotAction(*a) for a in actions], villain_cards=villain_cards)


RIVER_FACING_BET = (("hero", "call"), ("villain", "check"), ("villain", "check"), ("hero", "check"),
                    ("villain", "check"), ("hero", "check"), ("villain", "bet", 200))
QUADS_BOARD = ("As", "Ac", "7d", "7h", "2c")


# ----------------------------------------------------------------- explanation
def test_preflop_explanation_has_frequency_equity_reason_but_no_ev(store):
    result = advise(spot(), store=store)
    shown = result["explain"]
    assert shown["source"] == "preflop_chart" and shown["ev"] is None
    assert shown["frequency"] == pytest.approx(next(o["frequency"] for o in shown["options"] if o["label"] == shown["chosen"]))
    assert sum(o["frequency"] for o in shown["options"]) == pytest.approx(1.0, abs=1e-3)
    assert 0.5 < shown["equity"] < 0.75 and shown["opponent_range"]["effective_combos"] > 0
    assert "preflop chart" in shown["reason"] and "equity" in shown["reason"] and shown["reason"].endswith(".")


def test_postflop_explanation_has_consistent_action_evs(store):
    result = advise(spot(*RIVER_FACING_BET, board=QUADS_BOARD, cards=("Ah", "Ad")), store=store)
    shown = result["explain"]
    assert shown["source"] == "postflop_solve"
    by_label = {o["label"]: o for o in shown["options"]}
    assert all("ev" in option for option in by_label.values())
    fold = by_label["fold"]["ev"]
    assert fold == pytest.approx(0.0, abs=0.5)  # giving up now is the baseline
    call = next(o["ev"] for label, o in by_label.items() if label.startswith("call"))
    assert call > 50  # quads facing a river bet win the bet at least
    assert shown["ev"] == next(o["ev"] for o in shown["options"] if o["label"] == shown["chosen"])
    assert shown["equity"] > 0.9 and "EV" in shown["reason"] and shown["ev_note"]


def test_explanation_does_not_change_the_recommendation(store):
    from solver.bot import SolverBot
    first = advise(spot(*RIVER_FACING_BET, board=QUADS_BOARD, cards=("Ah", "Ad")), store=store)
    again = advise(spot(*RIVER_FACING_BET, board=QUADS_BOARD, cards=("Ah", "Ad")), store=store)
    assert first["advice"] == again["advice"] and first["explain"] == again["explain"]
    assert SolverBot.explain_ev is False  # simulations and benchmarks do not pay for it


def test_labels_read_like_the_coach_screen():
    assert [explain.pretty(label) for label in ("raise_250", "bet_300", "all_in", "call", "fold")] == ["Raise to 250", "Bet 300", "All-in", "Call", "Fold"]


def test_explain_build_handles_fallback_and_missing_explanations():
    assert explain.build({"action": "fold"}, None) is None
    fallback = explain.build({"action": "check"}, {"source": "fallback", "reason": "ReplayError: x"})
    assert "rule-based" in fallback["reason"] and fallback["options"] == []


def test_reason_mentions_mixing_range_width_and_exploit():
    explanation = {"source": "postflop_solve", "labels": ["check", "bet 50%"], "probabilities": [0.4, 0.6], "chosen": "bet 50%",
                   "action_ev": [120.0, 150.0], "hero_equity_vs_range": 0.62, "villain_effective_combos": 80.0,
                   "exploit": {"active": True, "locked_nodes": 2, "classification": "loose_passive", "hands_observed": 30}}
    shown = explain.build({"action": "bet", "amount": 300}, explanation)
    assert shown["ev"] == 150.0 and shown["frequency"] == 0.6 and shown["exploiting"] is True
    for fragment in ("60%", "mixes", "62%", "narrow", "+150", "best EV", "loose passive", "30 logged hands"):
        assert fragment in shown["reason"], fragment


# ------------------------------------------------------------------ type label
def test_type_label_reports_confidence_and_sample_size(store):
    log_hand(spot(("hero", "raise", 250), ("villain", "fold")), "Reg", store)
    thin = profile_summary(profile_for(store, "Reg").snapshot())["label"]
    assert thin == {"type": "unknown", "confidence": "very_low", "hands": 1, "decisions": 1, "assigned": False}
    for _ in range(24):
        log_hand(spot(("villain", "raise", 250), ("hero", "fold"), position="big_blind"), "Maniac", store)
    label = profile_summary(profile_for(store, "Maniac").snapshot())["label"]
    assert label["type"] == "loose_aggressive" and label["assigned"] is True
    assert label["hands"] == 24 and label["decisions"] == 24 and label["confidence"] == "medium"


def test_advice_carries_the_opponent_label(store):
    for _ in range(3):
        log_hand(spot(("hero", "raise", 250), ("villain", "fold")), "Reg", store)
    profile = advise(spot(), opponent="Reg", store=store)["opponent_profile"]
    assert profile["label"]["hands"] == 3 and profile["label"]["assigned"] is False


# ---------------------------------------------------------------------- review
def test_review_of_an_empty_log(store):
    result = review(store)
    assert result["results"]["hands"] == 0 and result["results"]["bb_per_100"] is None
    assert result["leaks"] == [] and result["by_opponent"] == []


def test_review_stats_results_and_per_opponent_breakdown(store):
    for _ in range(25):
        log_hand(spot(("hero", "raise", 250), ("villain", "fold")), "Reg", store)
    for _ in range(4):
        log_hand(spot(("hero", "raise", 250), ("villain", "fold")), "Fish", store)
    result = review(store)
    assert result["results"]["hands"] == 29 and result["results"]["net_bb"] == 29.0
    assert result["results"]["bb_per_100"] == 100.0
    assert result["stats"]["vpip"]["frequency"] == 1.0 and result["stats"]["pfr"]["frequency"] == 1.0
    assert result["stats"]["vpip"]["opportunities"] == 29 and result["stats"]["vpip"]["confidence"] == "medium"
    assert result["leaks"] == []
    assert [(row["opponent"], row["hands"], row["net_bb"]) for row in result["by_opponent"]] == [("Fish", 4, 4.0), ("Reg", 25, 25.0)]
    only = review(store, "Fish")
    assert only["results"]["hands"] == 4 and only["opponent"] == "Fish"


def test_review_flags_leaks_only_with_enough_hands(store):
    for _ in range(19):
        log_hand(spot(("villain", "raise", 250), ("hero", "fold"), position="big_blind"), "Reg", store)
    assert review(store)["leaks"] == []
    log_hand(spot(("villain", "raise", 250), ("hero", "fold"), position="big_blind"), "Reg", store)
    result = review(store)
    flagged = {item["stat"] for item in result["leaks"]}
    assert {"vpip", "fold_to_preflop_raise"} <= flagged
    assert result["results"]["net_bb"] == -20.0 * 1.0
    item = next(item for item in result["leaks"] if item["stat"] == "fold_to_preflop_raise")
    assert item["opportunities"] == 20 and item["frequency"] == 1.0 and item["confidence"] == "medium" and item["advice"]


def test_review_counts_showdown_results_only_when_known(store):
    showdown = [("hero", "call"), ("villain", "check"), ("villain", "check"), ("hero", "check"),
                ("villain", "check"), ("hero", "check"), ("villain", "check"), ("hero", "check")]
    board = ("2c", "7d", "9h", "Js", "3c")
    log_hand(spot(*showdown, board=board, villain_cards=["Qh", "Qd"]), "Reg", store)
    log_hand(spot(*showdown, board=board), "Reg", store)
    results = review(store)["results"]
    assert results["hands"] == 2 and results["showdowns"] == 2
    assert results["showdowns_with_known_result"] == 1 and results["hands_with_known_result"] == 1
    assert results["net_bb"] == -1.0


def test_leak_rules_need_a_sample_and_a_threshold():
    def stat(frequency, opportunities):
        return {"frequency": frequency, "opportunities": opportunities, "occurrences": 0, "confidence": "low"}
    base = {name: stat(0.5, 40) for name in ("vpip", "pfr", "three_bet", "fold_to_preflop_raise", "postflop_bet", "fold_to_bet", "showdown_win")}
    assert leaks(base) == []
    assert [item["stat"] for item in leaks({**base, "fold_to_bet": stat(0.7, 40)})] == ["fold_to_bet"]
    assert leaks({**base, "fold_to_bet": stat(0.7, 19)}) == []
    assert [item["stat"] for item in leaks({**base, "pfr": stat(0.1, 40)})] == ["pfr"]


def test_review_api(store):
    client = TestClient(main.app)
    for _ in range(2):
        client.post("/api/coach/hands", json={"hero_cards": ["As", "Kd"], "opponent": "Reg",
                                              "actions": [{"actor": "hero", "action": "raise", "amount": 250}, {"actor": "villain", "action": "fold"}]})
    everyone = client.get("/api/coach/review")
    assert everyone.status_code == 200 and everyone.json()["results"]["hands"] == 2
    assert client.get("/api/coach/review", params={"opponent": "Reg"}).json()["opponent"] == "Reg"
    assert client.get("/api/coach/review", params={"opponent": "Nobody"}).json()["results"]["hands"] == 0
    advice = client.post("/api/coach/advise", json={"hero_cards": ["As", "Kd"]}).json()
    assert advice["explain"]["reason"]


# ------------------------------------------------------------ hardening (step 4)
def test_preflop_labels_match_the_returned_action_when_facing_a_raise(store):
    # AKo in the big blind facing a 300 raise: the chart's raise size is rescaled to the real raise.
    result = advise(spot(("villain", "raise", 300), position="big_blind"), store=store)
    advice, explanation = result["advice"], result["explanation"]
    assert "concrete_labels" not in explanation
    assert len(explanation["labels"]) == len(explanation["probabilities"])
    assert len(set(explanation["labels"])) == len(explanation["labels"])
    played = advice["action"] if advice["amount"] is None else f"{advice['action']}_{advice['amount']}"
    assert explanation["chosen"] == played
    assert result["explain"]["chosen"] == played
    assert abs(sum(explanation["probabilities"]) - 1) < 0.01


def test_concretize_relabels_and_merges_options_that_land_on_the_same_play():
    raw = {"labels": ["fold", "call", "raise_750", "all_in"], "probabilities": [0.1, 0.2, 0.3, 0.4], "chosen": "raise_750",
           "concrete_labels": ["fold", "call", "all_in", "all_in"], "action_ev": [0.0, 10.0, 20.0, 40.0]}
    shown = explain.concretize(raw)
    assert shown["labels"] == ["fold", "call", "all_in"] and shown["chosen"] == "all_in"
    assert shown["probabilities"] == [0.1, 0.2, 0.7]
    assert shown["action_ev"] == [0.0, 10.0, round((0.3 * 20 + 0.4 * 40) / 0.7, 1)]
    assert "concrete_labels" not in shown
    assert explain.concretize(None) is None
    plain = {"labels": ["check"], "probabilities": [1.0], "chosen": "check"}
    assert explain.concretize(plain) is plain


def test_adjusted_flag_only_when_the_opponent_read_changed_the_strategy(store):
    log_hand(spot(("hero", "fold")), "Fresh", store)  # one hand: the model exists but has nothing confident
    result = advise(spot(), opponent="Fresh", store=store)
    locked = (result["explanation"]["exploit"] or {}).get("locked_nodes")
    assert result["exploiting"] is True and result["adjusted"] is bool(locked)
    assert advise(spot(), store=store)["adjusted"] is False
