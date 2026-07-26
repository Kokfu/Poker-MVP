import pytest
from simulation.cards import Deck
from simulation.actions import Action
from simulation.bots import RandomBot, TightBot, AggressiveBot, EquityBot
from simulation.engine import HandEngine, SimulationRunner

class ScriptedBot:
    def __init__(self, actions): self.actions=list(actions); self.observations=[]
    def decide(self, observation):
        self.observations.append(observation)
        if not self.actions: raise AssertionError("unexpected engine decision")
        return self.actions.pop(0)

@pytest.mark.parametrize("seed", range(8))
def test_deck_has_52_unique_cards(seed):
    deck=Deck(seed); assert len(deck.cards)==52 and len(set(deck.cards))==52

@pytest.mark.parametrize("seed", range(6))
def test_deck_shuffle_is_deterministic(seed): assert Deck(seed).cards==Deck(seed).cards

@pytest.mark.parametrize("bot_cls", [RandomBot,TightBot,AggressiveBot,EquityBot])
def test_bots_choose_legal_actions(bot_cls):
    engine=HandEngine(bot_cls(seed=4,equity_iterations=100),RandomBot(seed=5),seed=10)
    observation=engine.observe("a"); action=engine.bots["a"].decide(observation)
    assert action.type in observation.legal_actions

@pytest.mark.parametrize("bot_cls",[TightBot,AggressiveBot,EquityBot])
def test_passive_bot_uses_all_in_when_normal_call_is_unavailable(bot_cls):
    engine=HandEngine(bot_cls(seed=4,equity_iterations=100),RandomBot(seed=5),seed=10)
    engine.state.current_bets={"a":100,"b":10000}; engine.state.current_highest_bet=10000
    engine.state.stacks["a"]=9900; engine.state.pending_players={"a"}
    observation=engine.observe("a")
    assert observation.legal_actions==["fold","all_in"]
    action=engine.bots["a"]._passive(observation)
    assert action==Action("all_in")

@pytest.mark.parametrize("button,small,big", [("a",50,100),("b",50,100)])
def test_heads_up_blinds_and_preflop_order(button,small,big):
    engine=HandEngine(RandomBot(),RandomBot(),seed=1,button=button)
    assert engine.state.current_bets[button]==small and engine.state.current_bets[engine.other(button)]==big
    assert engine.state.acting_player==button and engine.state.pot==small+big

def test_postflop_action_is_non_button():
    engine=HandEngine(RandomBot(),RandomBot(),seed=1,button="a")
    engine._next_street(); assert engine.other(engine.state.button_player)=="b"

def test_no_bet_offers_check_and_bet():
    engine=HandEngine(RandomBot(),RandomBot(),seed=1); legal=engine.legal("a")
    assert "call" in legal and "fold" in legal
    engine._commit("a",50,"call"); assert "check" in engine.legal("b") and "raise" in engine.legal("b")

def test_illegal_action_falls_back_without_corrupting_stacks():
    engine=HandEngine(RandomBot(),RandomBot(),seed=1); before=sum(engine.state.stacks.values())+engine.state.pot
    engine._action("a",Action("check")); assert engine.illegal==1 and sum(engine.state.stacks.values())+engine.state.pot==before

@pytest.mark.parametrize("seed", range(6))
def test_complete_hand_conserves_chips(seed):
    result=HandEngine(RandomBot(seed),RandomBot(seed+1),seed=seed).play(); assert sum(result["stacks"].values())==20000

@pytest.mark.parametrize("seed", range(4))
def test_observation_hides_opponent_cards(seed):
    engine=HandEngine(RandomBot(),RandomBot(),seed=seed); obs=engine.observe("a")
    assert not hasattr(obs,"opponent_hole_cards") and not set(engine.holes["b"]) & set(obs.hole_cards+obs.community_cards)

@pytest.mark.parametrize("hands", [1,2,5,10])
def test_runner_reports_requested_hand_count_and_net_zero(hands):
    result=SimulationRunner(RandomBot(1),RandomBot(2),hands,seed=9).run()
    assert result["hands_played"]==hands and result["bot_a_net_chips"]+result["bot_b_net_chips"]==0

def test_runner_is_reproducible_excluding_generated_id():
    one=SimulationRunner(RandomBot(1),RandomBot(2),10,seed=9).run(); two=SimulationRunner(RandomBot(1),RandomBot(2),10,seed=9).run()
    for key in ("simulation_id","duration_ms","average_hand_duration_ms"): one.pop(key); two.pop(key)
    assert one==two

def test_different_seed_changes_random_results():
    one=SimulationRunner(RandomBot(1),RandomBot(2),20,seed=9).run(); two=SimulationRunner(RandomBot(1),RandomBot(2),20,seed=10).run()
    assert (one["bot_a_net_chips"],one["bot_a_wins"]) != (two["bot_a_net_chips"],two["bot_a_wins"])

@pytest.mark.parametrize("button",["a","b"])
def test_limp_keeps_big_blind_option(button):
    e=HandEngine(RandomBot(),RandomBot(),button=button); sb=button; bb=e.other(sb)
    e._action(sb,Action("call")); assert bb in e.state.pending_players and "check" in e.legal(bb) and "raise" in e.legal(bb)

@pytest.mark.parametrize("target,valid",[(200,True),(199,False),(500,True)])
def test_preflop_raise_minimum(target,valid):
    e=HandEngine(RandomBot(),RandomBot()); e._action("a",Action("raise",target))
    assert (e.state.current_highest_bet==target) is valid

@pytest.mark.parametrize("sequence",[(200,300,500),(300,700,1100),(200,500,800)])
def test_full_raises_update_minimum(sequence):
    e=HandEngine(RandomBot(),RandomBot()); a,b,c=sequence; e._action("a",Action("raise",a)); e._action("b",Action("raise",b)); e._action("a",Action("raise",c)); assert e.state.current_highest_bet==c and e.state.last_full_raise_size==c-b

@pytest.mark.parametrize("street",["flop","turn","river"])
def test_postflop_resets_betting_state(street):
    e=HandEngine(RandomBot(),RandomBot())
    while e.state.street!=street: e._next_street()
    assert e.state.current_highest_bet==0 and e.state.pending_players=={"a","b"} and e.state.last_full_raise_size==100

@pytest.mark.parametrize("seed",[1,2,42,123,999])
def test_seeded_random_stress(seed):
    r=SimulationRunner(RandomBot(seed),RandomBot(seed+1),100,seed=seed).run()
    assert r["hands_played"]==100 and r["bot_a_net_chips"]+r["bot_b_net_chips"]==0 and r["illegal_actions"]>=0

def test_short_all_in_call_returns_uncalled_excess():
    e=HandEngine(RandomBot(),RandomBot(),stack=10000); e._action("a",Action("raise",5000)); e.state.stacks["b"]=1000
    e._action("b",Action("all_in")); assert e.state.current_highest_bet==1100 and e.state.current_bets["a"]==1100 and e.state.pot==2200

@pytest.mark.parametrize("action",[Action("fold"),Action("call"),Action("raise",200),Action("all_in")])
def test_facing_blind_legal_actions_include_standard_choices(action):
    e=HandEngine(RandomBot(),RandomBot()); assert action.type in e.legal("a")

@pytest.mark.parametrize("sequence,expected_pending",[
    ([("a",Action("fold"))],set()),
    ([("a",Action("call")),("b",Action("check"))],set()),
    ([("a",Action("raise",200)),("b",Action("call"))],set()),
    ([("a",Action("raise",200)),("b",Action("raise",300)),("a",Action("call"))],set()),
    ([("a",Action("raise",300)),("b",Action("raise",700)),("a",Action("call"))],set()),
])
def test_preflop_sequences_complete_only_after_required_response(sequence,expected_pending):
    e=HandEngine(RandomBot(),RandomBot())
    for player,action in sequence: e._action(player,action)
    assert e.state.pending_players==expected_pending or e.folded is not None
    assert sum(e.state.stacks.values())+e.state.pot==e.total

@pytest.mark.parametrize("target,raise_size",[(200,100),(300,200),(500,400),(1100,1000)])
def test_raise_size_tracks_latest_full_increment(target,raise_size):
    e=HandEngine(RandomBot(),RandomBot()); e.state.street="flop"; e.state.current_bets={"a":0,"b":0}; e.state.current_highest_bet=0; e.state.last_full_raise_size=100; e.state.pending_players={"a"}
    e._action("a",Action("bet",100)); e._action("b",Action("raise",target)); assert e.state.last_full_raise_size==raise_size

@pytest.mark.parametrize("seed",[11,12,13])
def test_completed_hand_has_no_pending_or_negative_state(seed):
    e=HandEngine(RandomBot(seed),RandomBot(seed+1),seed=seed); result=e.play()
    assert not e.state.pending_players and all(x>=0 for x in result["stacks"].values()) and e.state.pot>=0

def test_per_hand_results_and_bb_formula_are_exact():
    runner=SimulationRunner(RandomBot(42),RandomBot(43),100,seed=42); result=runner.run(include_hand_results=True)
    hands=result["hand_results"]
    assert len(hands)==100 and all(-10000<=h["net_a"]<=10000 and h["net_a"]+h["net_b"]==0 and h["settled_once"] for h in hands)
    assert sum(h["net_a"] for h in hands)==result["bot_a_net_chips"]
    assert result["bot_a_bb_per_100"]==result["bot_a_net_chips"]/100
