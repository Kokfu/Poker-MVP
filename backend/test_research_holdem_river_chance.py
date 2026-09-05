"""Direct Phase 4G acceptance fixtures for sequential future public chance."""
from __future__ import annotations
import math, random
import pytest
from research.mccfr import external_sampling_regret_updates, external_sampling_strategy_sum_increment
from research.holdem.river_subgame import FIXED_FLOP, RiverHoldemState, river_subgame_convention
from research.holdem.river_exact import reduced_river_roots, reduced_river_report
from research.holdem.river_mccfr import RiverChanceExternalSamplingMCCFRTrainer
from research.holdem.diagnostics_4g import river_tree_diagnostics, validate_river_tree
from research.holdem.diagnostics_4g import reachable_infoset_universe
from research.holdem.scaling_4g import phase_4f_vs_4g_scaling_report
from research.holdem.cfr import HoldemSubgameCFRTrainer

def first(state,kind):return next(a for a in state.legal_actions if a.action_type==kind)
def checks_to_chance(state):
    a=state.apply(first(state,"check")); return a.apply(first(a,"check"))
def profiles_close(a,b):
    assert a.keys()==b.keys()
    for key in a:assert a[key]==pytest.approx(b[key],abs=1e-12)

def test_conditional_river_removal_is_complete_uniform_and_turn_dependent():
    root=RiverHoldemState(("Ah","Ad"),("Kh","Kc")); turn_chance=checks_to_chance(root)
    assert turn_chance.remaining_turn_cards()==("Qs","Js","Ts")
    children={card:child for card,child,_ in turn_chance.chance_outcomes()}
    assert children["Qs"].remaining_river_cards()==("Js","Ts")
    assert children["Js"].remaining_river_cards()==("Qs","Ts")
    river_chance=checks_to_chance(children["Qs"])
    outcomes=river_chance.chance_outcomes()
    assert {card for card,_,_ in outcomes}=={"Js","Ts"}
    assert sum(p for _,_,p in outcomes)==pytest.approx(1); assert all(p==pytest.approx(.5) for _,_,p in outcomes)
    for card,child,_ in outcomes:assert card not in set(FIXED_FLOP+root.player0_cards+root.player1_cards+("Qs",)) and child.river_card==card

def test_information_sets_preserve_private_and_future_card_privacy():
    a=RiverHoldemState(("Ah","Ad"),("Kh","Kc")); b=RiverHoldemState(("Ah","Ad"),("Qs","Js"))
    assert a.information_set()==b.information_set() # hidden opponent cards
    flop=checks_to_chance(a); turn_a={c:s for c,s,_ in flop.chance_outcomes()}
    assert a.information_set()==RiverHoldemState(("Ah","Ad"),("Kh","Kc"),deck=a.deck).information_set()
    turn=turn_a["Qs"]
    assert turn.decision_state().board_cards==FIXED_FLOP+("Qs",)
    river=checks_to_chance(turn); rchildren={c:s for c,s,_ in river.chance_outcomes()}
    assert turn.information_set()==RiverHoldemState(("Ah","Ad"),("Kh","Kc"),flop_history=flop.flop_history,turn_card="Qs",deck=a.deck).information_set()
    assert rchildren["Js"].decision_state().board_cards==FIXED_FLOP+("Qs","Js")
    assert all(c not in a.information_set() for c in flop.remaining_turn_cards())
    assert all(c not in turn.information_set() for c in river.remaining_river_cards())

def test_both_street_transitions_and_river_showdown_accounting():
    root=RiverHoldemState(("Ah","Ad"),("Kh","Kc")); flop=checks_to_chance(root)
    turn=flop.chance_outcomes()[0][1]
    assert turn.decision_state().hero_street_commitment==0 and turn.decision_state().pot==100
    opened=turn.apply(first(turn,"bet")); turn_to_river=opened.apply(first(opened,"call")); assert turn_to_river.chance
    river=turn_to_river.chance_outcomes()[0][1]; d=river.decision_state()
    assert d.street=="river" and d.hero_street_commitment==0 and d.opponent_street_commitment==0 and d.pot==200 and d.hero_stack==d.opponent_stack==50
    checked=checks_to_chance(river); assert checked.terminal and checked.utility(0)==-checked.utility(1)
    # Fold, call and check/check leave no future chance/action possibility.
    bet=river.apply(first(river,"bet")); folded=bet.apply(first(bet,"fold")); called=bet.apply(first(bet,"call"))
    assert folded.terminal and called.terminal and not folded.legal_actions and not called.legal_actions
    assert all(math.isfinite(x) for x in (checked.utility_p0(),folded.utility_p0(),called.utility_p0()))

def test_river_showdown_has_hero_villain_and_representable_tie_outcomes():
    def showdown(root, turn_card, river_card):
        turn=checks_to_chance(root); turn=next(child for card,child,_ in turn.chance_outcomes() if card==turn_card)
        river=checks_to_chance(turn); river=next(child for card,child,_ in river.chance_outcomes() if card==river_card)
        return checks_to_chance(river)
    hero=showdown(RiverHoldemState(("Ah","Ad"),("Kh","Kc")),"Qs","Js")
    villain=showdown(RiverHoldemState(("Kh","Kc"),("Ah","Ad")),"Qs","Js")
    tie=showdown(RiverHoldemState(("Ah","Kh"),("Ad","Kc")),"Qs","Js")
    assert hero.utility_p0()>0 and villain.utility_p0()<0 and tie.utility_p0()==0
    assert all(state.utility(0)==-state.utility(1) for state in (hero,villain,tie))

def test_exact_three_street_control_is_deterministic_and_chance_order_invariant():
    forward=HoldemSubgameCFRTrainer(roots=reduced_river_roots()).train(4)
    reverse=HoldemSubgameCFRTrainer(roots=reduced_river_roots(True)).train(4)
    profiles_close(forward.average_strategy(),reverse.average_strategy())
    report=reduced_river_report(4); m=report["metrics"]
    assert report["scope"].startswith("reduced exact three-street") and report["information_sets"]>0
    assert m["player0_ev"]==pytest.approx(-m["player1_ev"])

def test_sequential_chance_estimator_expectation_equals_independent_exact_sum():
    # Frozen, independently specified 50/50 opponent action choices after every
    # chance pair. q = q_private(1) * q_turn * q_river * q_opponent.
    state=checks_to_chance(RiverHoldemState(("Ah","Ad"),("Kh","Kc")))
    strategy={"check":.5,"bet":.5}; expected={a:0. for a in strategy}; exact={a:0. for a in strategy}; avg={a:0. for a in strategy}; avg_exact={a:0. for a in strategy}
    trajectories=0
    for _,turn,tp in state.chance_outcomes():
        river_node=checks_to_chance(turn)
        for _,river,rp in river_node.chance_outcomes():
            check=river.apply(first(river,"check")); bet=river.apply(first(river,"bet"))
            check_values=[]
            for opponent in (a for a in check.legal_actions if a.action_type=="check" or a.label=="bet_half_pot"):
                child=check.apply(opponent)
                check_values.append(child.utility_p0() if child.terminal else sum(child.apply(response).utility_p0()/2 for response in child.legal_actions if response.action_type in {"fold","call"}))
            bet_values=[bet.apply(a).utility_p0() for a in bet.legal_actions if a.action_type in {"fold","call"}]
            full={"check":sum(check_values)/len(check_values),"bet":sum(bet_values)/len(bet_values)}; value=sum(strategy[a]*full[a] for a in strategy)
            for a in strategy:exact[a]+=tp*rp*(full[a]-value); avg_exact[a]+=tp*rp*strategy[a]
            for cv in check_values:
                for bv in bet_values:
                    contribution=external_sampling_regret_updates(strategy,{"check":cv,"bet":bv}); q=tp*rp*.5*.5
                    for a in strategy:expected[a]+=q*contribution[a];avg[a]+=q*external_sampling_strategy_sum_increment(strategy,1,1)[a]
                    trajectories+=1
    assert trajectories==24 and expected==pytest.approx(exact,abs=1e-12) and avg==pytest.approx(avg_exact,abs=1e-12)

def test_mccfr_samples_two_conditional_chances_once_and_is_seeded():
    roots=reduced_river_roots(); a=RiverChanceExternalSamplingMCCFRTrainer(31,roots=roots).train(12,diagnostic=True); b=RiverChanceExternalSamplingMCCFRTrainer(31,roots=roots).train(12)
    assert a.last_trajectories==b.last_trajectories; profiles_close(a.average_strategy(),b.average_strategy())
    stages=[[x["chance_street"] for x in row["opponent_samples"] if "future_chance" in x] for row in a.last_trajectories]
    assert any("river" in row for row in stages)
    assert all("river" not in row or "turn" in row for row in stages)
    before=random.getstate(); RiverChanceExternalSamplingMCCFRTrainer(5,roots=roots).train(2); assert random.getstate()==before
    assert a.diagnostics(a.all_information_set_keys())["finite"]

def test_tree_is_measured_guarded_and_convention_is_explicit():
    report=river_tree_diagnostics(); assert report["bounded"] and report["full_tree_node_count"]<report["guardrail_nodes"] and report["information_sets_by_street"].keys()=={"flop","turn","river"}
    assert validate_river_tree()==[]
    convention=river_subgame_convention(); assert convention["no_future_card_after_river"] and "not full heads-up no-limit" in convention["scope"]

def test_reduced_exact_tree_is_exhaustively_traversable_and_order_invariant():
    forward=river_tree_diagnostics(reduced_river_roots())
    reverse=river_tree_diagnostics(reduced_river_roots(True))
    assert validate_river_tree(reduced_river_roots())==[]
    assert forward["tree_count_scope"]=="exact supplied roots"
    assert forward["full_tree_node_count"]==reverse["full_tree_node_count"]
    assert forward["turn_chance_nodes"] and forward["river_chance_nodes"]
    assert forward["player_decision_nodes"] and forward["terminal_nodes"]
    assert forward["validation_errors"]==[]

def test_reachable_universe_is_independent_of_sampling_and_drives_zero_visits():
    universe=dict(reachable_infoset_universe())
    assert set(universe.values())=={"flop","turn","river"}
    assert len(universe)==sum(sum(street==name for street in universe.values()) for name in ("flop","turn","river"))
    trainer=RiverChanceExternalSamplingMCCFRTrainer(13,roots=reduced_river_roots())
    known=next(iter(universe)); assert known not in trainer.infoset_visit_counts
    assert known in trainer.diagnostics(universe)["zero_visit_information_sets"]
    trainer.infoset_visit_counts[known]=1
    assert known not in trainer.diagnostics(universe)["zero_visit_information_sets"]
    assert "unreachable-key" not in universe

def test_phase_4f_vs_4g_scaling_report_uses_identical_accounting():
    report=phase_4f_vs_4g_scaling_report(iterations=5,seed=9)
    assert report["accounting"].startswith("one logical iteration")
    first,second=report["phase_4f"],report["phase_4g"]
    assert first["traversals"]==second["traversals"]==10
    assert second["tree_nodes"]>first["tree_nodes"] and second["chance_nodes"]>first["chance_nodes"]
    for row in (first,second): assert all(value >= 0 and math.isfinite(value) for value in (row["runtime_seconds"],row["nodes_per_logical_iteration"],row["strategy_regret_memory_bytes"]))
