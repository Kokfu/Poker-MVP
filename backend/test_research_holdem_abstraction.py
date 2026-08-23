"""Acceptance evidence for the Phase 4C research-only Hold'em abstraction."""
from __future__ import annotations

import copy
from dataclasses import replace

from research.holdem import HoldemAbstraction, abstraction_diagnostics, card_bucket
from simulation.actions import Action
from simulation.bots import RandomBot
from simulation.decision_state import build_decision_observation
from simulation.engine import HandEngine


def game(seed=19, *, button="a", stacks=None, stack=1_000, bb=100):
    return HandEngine(
        RandomBot(1), RandomBot(2), stack=stack, bb=bb, seed=seed,
        button=button, starting_stacks=stacks,
    )


def decision(engine, player=None):
    return build_decision_observation(engine, player or engine.state.acting_player).decision_state


def state(seed=19):
    return decision(game(seed), "a")


def postflop_engine(seed=20, *, stacks=None, button="a"):
    """A real, unopened flop after a limp/check, with the BB to act."""
    engine = game(seed, button=button, stacks=stacks)
    button_player = engine.state.button_player
    big_blind = engine.other(button_player)
    engine._action(button_player, Action("call"))
    engine._action(big_blind, Action("check"))
    engine._next_street()
    return engine


def action_by_label(actions, label):
    return next(action for action in actions if action.label == label)


def non_terminal_action(actions):
    return next(action for action in actions if action.action_type in {"bet", "raise", "check", "call"})


def test_card_buckets_are_explicit_for_all_streets_and_visible_state_only():
    base = state()
    preflop = replace(base, hole_cards=("As", "Ah"))
    flop = replace(base, street="flop", hole_cards=("As", "Kd"), board_cards=("Ac", "7h", "2d"))
    turn = replace(base, street="turn", hole_cards=("Qs", "Js"), board_cards=("Ts", "2s", "7d", "3c"))
    river = replace(base, street="river", hole_cards=("As", "Kd"), board_cards=("Qs", "Jh", "Tc", "2d", "3c"))
    assert card_bucket(preflop) == "preflop_premium"
    assert card_bucket(flop) == "postflop_pair"
    assert card_bucket(turn) == "postflop_draw"
    assert card_bucket(river) == "postflop_straight_plus"
    assert card_bucket(flop) == card_bucket(replace(flop, hand_id="another-visible-copy", hand_number=99))


def test_hidden_cards_and_unseen_deck_do_not_affect_card_bucket_or_key():
    engine = game(44)
    first = decision(engine, "a")
    bucket = card_bucket(first)
    key = HoldemAbstraction.information_set(first)
    engine.holes["b"] = ["2c", "3d"]
    engine.deck.cards.reverse()
    second = decision(engine, "a")
    assert card_bucket(second) == bucket
    assert HoldemAbstraction.information_set(second) == key


def test_future_board_privacy_and_information_set_determinism():
    engine = postflop_engine(75)
    before = decision(engine)
    key = HoldemAbstraction.information_set(before)
    actions = HoldemAbstraction.abstract_actions(before)
    engine.deck.cards[:] = list(reversed(engine.deck.cards))
    after = decision(engine)
    assert before.board_cards == after.board_cards
    assert key == HoldemAbstraction.information_set(after)
    assert actions == HoldemAbstraction.abstract_actions(after)
    assert key == HoldemAbstraction.information_set(before)


def test_semantic_actions_map_directly_to_their_concrete_engine_actions():
    preflop = state()
    preflop_actions = HoldemAbstraction.abstract_actions(preflop)
    for label in ("fold", "call", "all_in"):
        assert HoldemAbstraction.concretize(preflop, action_by_label(preflop_actions, label)) == Action(label)
    unopened = decision(postflop_engine())
    for label in ("check", "all_in"):
        assert HoldemAbstraction.concretize(unopened, action_by_label(HoldemAbstraction.abstract_actions(unopened), label)) == Action(label)
    engine = postflop_engine()
    engine._action("b", Action("bet", 200))
    facing_bet = decision(engine, "a")
    for label in ("fold", "call", "all_in"):
        assert HoldemAbstraction.concretize(facing_bet, action_by_label(HoldemAbstraction.abstract_actions(facing_bet), label)) == Action(label)


def test_bet_and_raise_sizing_representatives_are_direct_bounded_total_targets():
    unopened = decision(postflop_engine())
    for label, target in {"bet_half_pot": 100, "bet_three_quarter_pot": 150, "bet_pot_and_quarter": 250}.items():
        abstract = action_by_label(HoldemAbstraction.abstract_actions(unopened), label)
        assert abstract.target_total == target
        assert HoldemAbstraction.concretize(unopened, abstract) == Action("bet", target)
        assert unopened.minimum_legal_target <= target <= unopened.maximum_legal_target
    facing_engine = postflop_engine()
    facing_engine._action("b", Action("bet", 100))
    facing = decision(facing_engine, "a")
    for label, target in {"raise_half_pot": 200, "raise_three_quarter_pot": 225, "raise_pot_and_quarter": 375}.items():
        abstract = action_by_label(HoldemAbstraction.abstract_actions(facing), label)
        assert abstract.target_total == target
        assert HoldemAbstraction.concretize(facing, abstract) == Action("raise", target)
        assert facing.minimum_legal_target <= abstract.target_total <= facing.maximum_legal_target


def test_exact_minimum_maximum_and_single_target_intervals_are_preserved():
    normal = decision(postflop_engine(stacks={"a": 1_000, "b": 350}))
    assert (normal.minimum_legal_target, normal.maximum_legal_target) == (100, 250)
    actions = HoldemAbstraction.abstract_actions(normal)
    minimum = action_by_label(actions, "bet_half_pot")
    maximum = action_by_label(actions, "bet_pot_and_quarter")
    assert minimum.target_total == normal.minimum_legal_target
    assert maximum.target_total == normal.maximum_legal_target
    assert HoldemAbstraction.concretize(normal, minimum) == Action("bet", 100)
    assert HoldemAbstraction.concretize(normal, maximum) == Action("bet", 250)
    single = decision(postflop_engine(stacks={"a": 1_000, "b": 200}))
    assert (single.minimum_legal_target, single.maximum_legal_target) == (100, 100)
    sizing = [action for action in HoldemAbstraction.abstract_actions(single) if action.action_type == "bet"]
    assert [(action.label, action.target_total) for action in sizing] == [("bet_half_pot", 100)]
    assert HoldemAbstraction.concretize(single, sizing[0]) == Action("bet", 100)


def test_empty_normal_intervals_and_short_all_ins_never_manufacture_a_fake_target():
    empty = decision(postflop_engine(stacks={"a": 1_000, "b": 150}))
    assert empty.minimum_legal_target == 100 and empty.maximum_legal_target == 50
    assert empty.legal_actions == ("check", "all_in")
    assert [(item.action_type, item.target_total) for item in HoldemAbstraction.abstract_actions(empty)] == [("check", None), ("all_in", None)]
    assert HoldemAbstraction.concretize(empty, action_by_label(HoldemAbstraction.abstract_actions(empty), "all_in")) == Action("all_in")
    engine = game(stacks={"a": 1_000, "b": 250})
    engine._action("a", Action("raise", 300))
    short = decision(engine, "b")
    assert short.minimum_legal_target is None and short.legal_actions == ("fold", "all_in")
    assert [(item.action_type, item.target_total) for item in HoldemAbstraction.abstract_actions(short)] == [("fold", None), ("all_in", None)]
    engine._action("b", HoldemAbstraction.concretize(short, action_by_label(HoldemAbstraction.abstract_actions(short), "all_in")))
    assert engine.illegal == 0


def test_total_target_means_final_street_commitment_not_additional_chips():
    engine = game()
    before = decision(engine, "a")
    concrete = HoldemAbstraction.concretize(before, action_by_label(HoldemAbstraction.abstract_actions(before), "raise_pot_and_quarter"))
    assert (before.hero_street_commitment, before.hero_stack, concrete.amount) == (50, 950, 238)
    engine._action("a", concrete)
    assert engine.state.current_bets["a"] == 238
    assert engine.state.stacks["a"] == 762
    assert before.hero_stack - engine.state.stacks["a"] == concrete.amount - before.hero_street_commitment
    assert engine.illegal == 0


def _street_factories():
    def preflop(): return game(91), "a"
    def flop():
        engine = postflop_engine(92)
        return engine, engine.state.acting_player
    def turn():
        engine = postflop_engine(93)
        engine._action("b", Action("check")); engine._action("a", Action("check")); engine._next_street()
        return engine, engine.state.acting_player
    def river():
        engine, _ = turn()
        engine._action("b", Action("check")); engine._action("a", Action("check")); engine._next_street()
        return engine, engine.state.acting_player
    return {"preflop": preflop, "flop": flop, "turn": turn, "river": river}


def test_round_trip_is_deterministic_and_legal_on_every_street():
    for street, factory in _street_factories().items():
        engine, player = factory()
        current = decision(engine, player)
        abstract = non_terminal_action(HoldemAbstraction.abstract_actions(current))
        concrete = HoldemAbstraction.concretize(current, abstract)
        repeat_engine, repeat_player = factory()
        repeat = decision(repeat_engine, repeat_player)
        repeat_abstract = non_terminal_action(HoldemAbstraction.abstract_actions(repeat))
        assert (HoldemAbstraction.information_set(current), abstract, concrete) == (HoldemAbstraction.information_set(repeat), repeat_abstract, HoldemAbstraction.concretize(repeat, repeat_abstract)), street
        engine._action(player, concrete)
        assert engine.illegal == 0


def _advance_path(engine, *, aggressive_street=None):
    """Return real decision states while choosing one deterministic legal path."""
    states = []
    player = engine.state.acting_player
    while engine.folded is None and engine.state.street in {"preflop", "flop", "turn", "river"}:
        current = decision(engine, player)
        states.append((copy.deepcopy(engine), player, current))
        abstract = HoldemAbstraction.abstract_actions(current)
        aggressive = next((item for item in abstract if item.action_type in {"bet", "raise"}), None)
        chosen = aggressive if aggressive is not None and current.street == aggressive_street else next((item for item in abstract if item.action_type in {"check", "call"}), None)
        if chosen is None:
            chosen = action_by_label(abstract, "all_in")
        engine._action(player, HoldemAbstraction.concretize(current, chosen))
        if engine.folded is not None:
            break
        if not engine.state.pending_players:
            if engine.state.street == "river":
                break
            engine._next_street(); player = engine.state.acting_player
        else:
            player = engine.other(player)
    return states


def _representative_origin_paths():
    paths = []
    for index, seed in enumerate(range(300, 324)):
        street = (None, "preflop", "flop", "turn")[index % 4]
        paths.extend(_advance_path(game(seed, button="a" if index % 2 == 0 else "b"), aggressive_street=street))
    return paths


def test_representative_real_corpus_has_measurable_reduction_and_meaningful_coverage():
    states = [item[2] for item in _representative_origin_paths()]
    report = abstraction_diagnostics(states)
    assert report == abstraction_diagnostics(states)
    assert {item.street for item in states} == {"preflop", "flop", "turn", "river"}
    assert {item.position for item in states} == {"in_position", "out_of_position"}
    assert report["concrete_states"] > report["abstract_states"] > 8
    assert report["compression_ratio"] > 1.0
    assert len(report["bucket_occupancy"]) >= 4
    assert len(report["geometry_occupancy"]["pot_bb"]) >= 2
    assert len(report["geometry_occupancy"]["spr"]) >= 2
    assert len(report["geometry_occupancy"]["call_pressure"]) >= 2
    assert report["action_abstraction"]["coverage"] == 1.0
    assert report["action_abstraction"]["mapping_error_count"] == 0
    assert report["action_abstraction"]["concretization_attempts"] >= len(states)


def test_zero_fallback_stress_executes_every_generated_action_from_real_states():
    origins = _representative_origin_paths()
    empty_engine = postflop_engine(stacks={"a": 1_000, "b": 150})
    short_engine = game(stacks={"a": 1_000, "b": 250})
    short_engine._action("a", Action("raise", 300))
    origins.extend([(empty_engine, empty_engine.state.acting_player, decision(empty_engine)), (short_engine, "b", decision(short_engine, "b"))])
    metrics = {"decisions": len(origins), "attempts": 0, "illegal": 0, "fallbacks": 0, "target_errors": 0, "exceptions": 0, "conservation_failures": 0}
    for origin, player, current in origins:
        for abstract in HoldemAbstraction.abstract_actions(current):
            metrics["attempts"] += 1
            clone = copy.deepcopy(origin)
            try:
                clone._action(player, HoldemAbstraction.concretize(current, abstract))
            except ValueError:
                metrics["target_errors"] += 1
            except Exception:
                metrics["exceptions"] += 1
            else:
                metrics["illegal"] += clone.illegal
                metrics["fallbacks"] += len(clone.illegal_diagnostics)
                metrics["conservation_failures"] += int(sum(clone.state.stacks.values()) + clone.state.pot != clone.total)
    assert metrics["decisions"] >= 60
    assert metrics["attempts"] >= 150
    assert all(metrics[key] == 0 for key in ("illegal", "fallbacks", "target_errors", "exceptions", "conservation_failures"))


def test_diagnostics_report_empty_overloaded_and_normal_occupancy_honestly():
    base = state(); weak = replace(base, hole_cards=("7s", "2h")); premium = replace(base, hole_cards=("As", "Ah"))
    overloaded = abstraction_diagnostics([weak] * 8 + [premium] * 2)
    assert "postflop_air" in overloaded["empty_card_buckets"]
    assert overloaded["overloaded_card_buckets"] == ["preflop_weak"]
    assert overloaded["action_abstraction"]["coverage"] == 1.0
    assert overloaded["action_abstraction"]["mapping_error_count"] == 0
    assert overloaded["action_abstraction"]["concretization_attempts"] == sum(len(HoldemAbstraction.abstract_actions(item)) for item in [weak] * 8 + [premium] * 2)
    assert abstraction_diagnostics([weak] * 5 + [premium] * 5)["overloaded_card_buckets"] == []


def test_documented_intentional_aliases_and_visible_distinctions():
    base = state()
    scaled = decision(game(19, stack=2_000, bb=200), "a")
    assert (base.minimum_legal_target, base.maximum_legal_target, base.last_full_raise_size) == (200, 1_000, 100)
    assert (scaled.minimum_legal_target, scaled.maximum_legal_target, scaled.last_full_raise_size) == (400, 2_000, 200)
    assert HoldemAbstraction.information_set(base) == HoldemAbstraction.information_set(scaled)
    flop = replace(base, street="flop", hole_cards=("As", "Kd"), board_cards=("Ac", "7h", "2d"))
    different_texture = replace(flop, board_cards=("Ac", "7s", "2s"))
    assert card_bucket(flop) == card_bucket(different_texture) == "postflop_pair"
    assert HoldemAbstraction.information_set(flop) == HoldemAbstraction.information_set(different_texture)
    assert HoldemAbstraction.information_set(base) != HoldemAbstraction.information_set(replace(base, position="out_of_position"))
    assert HoldemAbstraction.information_set(base) != HoldemAbstraction.information_set(replace(base, hole_cards=("As", "Ah")))
