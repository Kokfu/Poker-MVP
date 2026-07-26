from __future__ import annotations
import time, uuid
from .cards import Deck
from .actions import Action
from .game_state import GameState, Observation
from .statistics import Statistics
from .dataset import JsonlDataset, SCHEMA_VERSION
from poker_analyzer import EVALUATOR

class HandEngine:
    """Authoritative local heads-up engine. Actions use target round commitment."""
    def __init__(self, bot_a, bot_b, stack=10000, bb=100, seed=None, hand_id="hand-0", button="a", dataset=None, simulation_id="local", hand_number=1, simulation_seed=None):
        self.bots={"a":bot_a,"b":bot_b}; self.bb=bb; self.sb=bb//2; self.deck=Deck(seed); self.holes={"a":self.deck.deal(2),"b":self.deck.deal(2)}; self.dataset=dataset or JsonlDataset()
        self.state=GameState(hand_id,button,button,stacks={"a":stack,"b":stack},current_bets={"a":0,"b":0},minimum_raise=bb,current_highest_bet=bb,last_full_raise_size=bb,pending_players={button},acted_since_full_raise={"a":False,"b":False},raising_reopened={"a":True,"b":True}); self.total=stack*2; self.starting_stacks={"a":stack,"b":stack}; self.folded=None; self.illegal=0; self.illegal_diagnostics=[]; self.simulation_id=simulation_id; self.simulation_seed=simulation_seed; self.hand_number=hand_number; self._records=[]; self.showdown_count=0; self.settlement_count=0
        self._commit(button,self.sb,"blind"); self._commit(self.other(button),self.bb,"blind"); self.state.amount_to_call=self.bb-self.sb
    def other(self,p): return "b" if p=="a" else "a"
    def _commit(self,p,amount,kind):
        amount=min(amount,self.state.stacks[p]); self.state.stacks[p]-=amount; self.state.current_bets[p]+=amount; self.state.pot+=amount
        if kind!="blind": self.state.action_history.append({"player":p,"type":kind,"amount":amount})
    def legal(self,p):
        call=self.state.current_highest_bet-self.state.current_bets[p]; stack=self.state.stacks[p]
        if call==0:
            actions=["check"]
            if not stack or not self.state.raising_reopened[p]: return actions
            if self.state.current_highest_bet==0: return actions+["bet","all_in"]
            maximum=self.state.current_bets[p]+stack
            minimum=self.state.current_highest_bet+self.state.last_full_raise_size
            if maximum>=minimum: actions.append("raise")
            if maximum>self.state.current_highest_bet: actions.append("all_in")
            return actions
        actions=["fold","call"]
        maximum=self.state.current_bets[p]+stack
        minimum=self.state.current_highest_bet+self.state.last_full_raise_size
        if stack and stack <= call: actions=["fold","all_in"]
        elif stack>call and self.state.raising_reopened[p]:
            if maximum >= minimum: actions += ["raise","all_in"]
            elif maximum > self.state.current_highest_bet: actions += ["all_in"]
        return actions
    def observe(self,p):
        call=self.state.current_highest_bet-self.state.current_bets[p]; maximum=self.state.current_bets[p]+self.state.stacks[p]
        can_increase = maximum > self.state.current_highest_bet and self.state.raising_reopened[p]
        minimum=(self.bb if self.state.current_highest_bet==0 else self.state.current_highest_bet+self.state.last_full_raise_size) if can_increase else None
        return Observation(self.state.hand_id,p,"BTN" if self.state.button_player==p else "BB",self.state.street,list(self.holes[p]),list(self.state.community_cards),self.state.pot,self.state.stacks[p],self.state.stacks[self.other(p)],self.state.current_bets[p],call,self.state.last_full_raise_size,minimum,maximum,maximum,self.legal(p),list(self.state.action_history))
    def _action(self,p,action):
        legal=self.legal(p); typ=action.type if action.type in legal else ("check" if "check" in legal else "fold")
        if typ!=action.type: self.illegal+=1; self.illegal_diagnostics.append({"reason":"ACTION_TYPE_NOT_ALLOWED","player":p,"requested":action.type,"target":action.amount,"legal":legal}); self.state.action_history.append({"player":p,"type":"illegal_action","requested":action.type})
        call=self.state.current_highest_bet-self.state.current_bets[p]
        if typ=="fold": self.folded=p; self.state.pending_players.clear(); self.state.action_history.append({"player":p,"type":"fold"}); return typ
        if typ=="check": self.state.pending_players.discard(p); self.state.acted_since_full_raise[p]=True; self.state.action_history.append({"player":p,"type":"check"}); return typ
        if typ=="call":
            self._commit(p,call,"call"); self.state.pending_players.discard(p); self.state.acted_since_full_raise[p]=True
            # A completed limp is not a closed preflop round: the BB retains its option.
            other=self.other(p)
            if self.state.street=="preflop" and p==self.state.button_player and not self.state.acted_since_full_raise[other]: self.state.pending_players.add(other)
            return typ
        if typ=="all_in":
            target=self.state.current_bets[p]+self.state.stacks[p]
            if target <= self.state.current_highest_bet:
                self._commit(p,self.state.stacks[p],"all_in")
                # Heads-up has no side pot: immediately return an unmatched overage.
                if target < self.state.current_highest_bet:
                    covering=self.other(p); excess=self.state.current_highest_bet-target
                    self.state.current_bets[covering]-=excess; self.state.stacks[covering]+=excess; self.state.pot-=excess; self.state.current_highest_bet=target
                self.state.pending_players.discard(p); self.state.acted_since_full_raise[p]=True; return typ
        else: target=action.amount or 0
        minimum=self.state.current_highest_bet+self.state.last_full_raise_size
        if target<minimum or target>self.state.current_bets[p]+self.state.stacks[p]:
            # A below-minimum all-in is a legal short raise only when it exceeds the wager.
            if not (typ=="all_in" and target>self.state.current_highest_bet):
                self.illegal+=1; self.illegal_diagnostics.append({"reason":"TARGET_OUT_OF_RANGE","player":p,"requested":typ,"target":target,"minimum":minimum,"maximum":self.state.current_bets[p]+self.state.stacks[p]}); return self._action(p,Action("check") if call==0 else Action("fold"))
        previous=self.state.current_highest_bet; increment=target-previous; self._commit(p,target-self.state.current_bets[p],typ); self.state.current_highest_bet=target
        full=increment>=self.state.last_full_raise_size
        if full:
            self.state.last_full_raise_size=increment; self.state.raising_reopened={"a":True,"b":True}; self.state.acted_since_full_raise={"a":False,"b":False}
        self.state.acted_since_full_raise[p]=True; other=self.other(p); self.state.pending_players={other}
        if not full: self.state.raising_reopened[other]=not self.state.acted_since_full_raise[other]
        return typ
    def _decision_record(self,p,obs,action,elapsed):
        target = None
        if action.type=="call": target=obs.current_bet+obs.amount_to_call
        elif action.type in ("bet","raise"): target=action.amount
        elif action.type=="all_in": target=obs.all_in_target_to
        classification={"fold":"fold","check":"free_check","call":"normal_call","bet":"opening_bet","raise":"full_raise"}.get(action.type)
        all_in_classification=None
        if action.type=="all_in":
            if target<self.state.current_highest_bet: all_in_classification="short_all_in_call"
            elif target==self.state.current_highest_bet: all_in_classification="exact_all_in_call"
            elif obs.minimum_target_to is not None and target<obs.minimum_target_to: all_in_classification="short_all_in_raise"
            else: all_in_classification="full_all_in_raise"
            classification=all_in_classification
        return {
            "schema_version":SCHEMA_VERSION,"simulation_id":self.simulation_id,"hand_id":self.state.hand_id,
            "hand_number":self.hand_number,"decision_index":len(self._records),"seed":self.simulation_seed,
            "bot_name":type(self.bots[p]).__name__,"acting_player":p,"position":obs.position,"street":obs.street,
            "hero_cards":obs.hole_cards,"board_cards":obs.community_cards,"hero_stack":obs.hero_stack,
            "opponent_stack":obs.opponent_stack,"starting_stack":self.starting_stacks[p],"big_blind":self.bb,
            "pot":obs.pot,"hero_street_commitment":obs.current_bet,
            "opponent_street_commitment":self.state.current_bets[self.other(p)],
            "current_highest_bet":self.state.current_highest_bet,"amount_to_call":obs.amount_to_call,
            "last_full_raise_size":obs.minimum_raise,"raising_reopened":self.state.raising_reopened[p],
            "pending_players":sorted(self.state.pending_players),"minimum_target_to":obs.minimum_target_to,
            "maximum_target_to":obs.maximum_target_to,"all_in_target_to":obs.all_in_target_to,
            "legal_actions":obs.legal_actions,"chosen_action":{"type":action.type,"amount":action.amount},
            "chosen_target_to":target,"action_classification":classification,
            "all_in_classification":all_in_classification,"decision_time_ms":elapsed,
        }
    def _round(self,first):
        p=first; acted=[]
        while self.folded is None and self.state.pending_players:
            if p not in self.state.pending_players: p=self.other(p)
            self.state.acting_player=p
            obs=self.observe(p); started=time.perf_counter(); action=self.bots[p].decide(obs); elapsed=(time.perf_counter()-started)*1000
            self._records.append(self._decision_record(p,obs,action,elapsed))
            typ=self._action(p,action); acted.append((p,typ,elapsed)); q=self.other(p)
            p=q
        return acted
    def _next_street(self):
        for p in self.state.current_bets: self.state.current_bets[p]=0
        self.state.current_highest_bet=0; self.state.last_full_raise_size=self.bb; self.state.pending_players={"a","b"}; self.state.acted_since_full_raise={"a":False,"b":False}; self.state.raising_reopened={"a":True,"b":True}; self.state.acting_player=self.other(self.state.button_player)
        if self.state.street=="preflop": self.state.street="flop"; self.state.community_cards+=self.deck.deal(3)
        elif self.state.street=="flop": self.state.street="turn"; self.state.community_cards+=self.deck.deal(1)
        elif self.state.street=="turn": self.state.street="river"; self.state.community_cards+=self.deck.deal(1)
    def play(self):
        decisions=[]
        for street in ("preflop","flop","turn","river"):
            if self.folded is not None: break
            if street!="preflop": self._next_street()
            if self.state.stacks["a"]==0 or self.state.stacks["b"]==0: continue
            decisions += self._round(self.state.button_player if street=="preflop" else self.other(self.state.button_player))
        if self.folded is not None: winner=self.other(self.folded); showdown=False
        else:
            self.state.street="showdown"; showdown=True; self.showdown_count+=1; sa=EVALUATOR.score(self.holes["a"],self.state.community_cards); sb=EVALUATOR.score(self.holes["b"],self.state.community_cards); winner="a" if sa<sb else "b" if sb<sa else None
        self.settlement_count+=1
        if winner is None: self.state.stacks["a"]+=self.state.pot//2; self.state.stacks["b"]+=self.state.pot-self.state.pot//2
        else: self.state.stacks[winner]+=self.state.pot
        self.state.pot=0; self.state.current_bets={"a":0,"b":0}; self.state.pending_players.clear(); self.state.street="complete"; assert sum(self.state.stacks.values())==self.total
        for record in self._records:
            player=record["acting_player"]; net=self.state.stacks[player]-self.starting_stacks[player]; record.update({"winner":winner,"showdown":showdown,"net_chips":net,"final_reward_bb":net/self.bb,"hand_ended_by":"showdown" if showdown else "fold"}); self.dataset.write(record)
        return {"winner":winner,"showdown":showdown,"stacks":dict(self.state.stacks),"illegal_actions":self.illegal,"illegal_diagnostics":self.illegal_diagnostics,"actions":decisions,"state":self.state}

class SimulationRunner:
    def __init__(self,bot_a,bot_b,hands=100,starting_stack_bb=100,seed=None,equity_iterations=1000,dataset_path=None,dataset_overwrite=False):
        self.bot_a=bot_a; self.bot_b=bot_b; self.hands=hands; self.seed=seed; self.bb=100; self.stack=starting_stack_bb*self.bb; self.equity_iterations=equity_iterations; self.dataset=JsonlDataset(dataset_path,dataset_overwrite)
    def run(self, include_hand_results: bool = False):
        import random
        rng=random.Random(self.seed); stats=Statistics(str(uuid.uuid4()),self.seed,type(self.bot_a).__name__,type(self.bot_b).__name__,self.bb); began=time.perf_counter(); self.hand_results=[]; self.illegal_diagnostics=[]
        for i in range(self.hands):
            engine=HandEngine(self.bot_a,self.bot_b,self.stack,self.bb,rng.randrange(2**31),f"hand-{i}","a" if i%2==0 else "b",self.dataset,stats.simulation_id,i+1,self.seed); result=engine.play(); stats.hands_played+=1; stats.illegal_actions+=result["illegal_actions"]
            self.illegal_diagnostics += [{**d,"hand_number":i+1} for d in result["illegal_diagnostics"]]
            delta=result["stacks"]["a"]-self.stack; stats.bot_a_net_chips+=delta; stats.bot_b_net_chips-=delta
            assert -self.stack <= delta <= self.stack and result["stacks"]["b"]-self.stack == -delta
            self.hand_results.append({"hand_number":i+1,"net_a":delta,"net_b":-delta,"settled_once":result["state"].pot==0 and not result["state"].pending_players})
            if result["winner"]=="a": stats.bot_a_wins+=1
            elif result["winner"]=="b": stats.bot_b_wins+=1
            else: stats.ties+=1
            stats.showdowns+=int(result["showdown"]); stats.fold_ended_hands+=int(not result["showdown"])
            for player,action,_ in result["actions"]: stats.record_action(player,action)
            for street in {x["type"] for x in result["state"].action_history if x["type"] not in ("blind",)}: pass
        stats.duration_ms=(time.perf_counter()-began)*1000; assert stats.bot_a_net_chips+stats.bot_b_net_chips==0
        output=stats.as_dict()
        if include_hand_results: output["hand_results"]=self.hand_results
        return output
