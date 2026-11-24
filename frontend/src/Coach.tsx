import { FormEvent, useEffect, useMemo, useState } from "react";
import CoachReview from "./CoachReview";
import CoachData from "./CoachData";
import CoachMultiway from "./CoachMultiway";
import { CardInput, PlayingCard } from "./CardInput";

type Actor = "hero" | "villain";
type ActionKind = "fold" | "check" | "call" | "bet" | "raise" | "all_in";
type SpotAction = { actor: Actor; action: ActionKind; amount?: number | null };

type SpotState = {
  street: string;
  pot: number;
  to_call: number;
  legal_actions: ActionKind[];
  minimum_target: number | null;
  maximum_target: number;
  hero_stack: number;
  villain_stack: number;
  board: string[];
};

type Explanation = {
  source: string;
  hero_equity_vs_range?: number;
  villain_effective_combos?: number;
  villain_top_classes?: { hand: string; share: number }[];
  villain_range_makeup?: { type: string; share: number }[];
  exploit?: { active: boolean; hands_observed?: number; classification?: string; locked_nodes?: number };
  reason?: string;
};

type Explain = {
  chosen: string | null;
  frequency: number | null;
  ev: number | null;
  ev_note?: string;
  equity?: number | null;
  options: { label: string; frequency: number; ev?: number }[];
  opponent_range: { effective_combos: number } | null;
  reason: string;
};

export function CoachStrategy({ options }: { options: Explain["options"] }) {
  if (options.length === 0) return null;
  return (
    <div className="coach-strategy">
      {options.map(({ label, frequency, ev }) => (
        <div key={label} className="coach-bar">
          <span>{describeLabel(label)}</span>
          <div><i style={{ width: `${Math.round(frequency * 100)}%` }} /></div>
          <b>{Math.round(frequency * 100)}%</b>
          {ev !== undefined && <small className="coach-ev" title="Chips you expect to win from here on, counting only chips still to put in (fold = 0)">EV {ev >= 0 ? "+" : ""}{Math.round(ev)}</small>}
        </div>
      ))}
    </div>
  );
}

type StatRead = { frequency: number; opportunities: number; confidence: string };
type Profile = {
  hands_observed: number;
  classification: string;
  label?: { type: string; confidence: string; hands: number; decisions: number; assigned: boolean };
  preflop: Record<string, StatRead>;
  postflop: Record<string, Record<string, StatRead>>;
};

type CoachResponse =
  | { status: "hero_to_act"; advice: { action: ActionKind; amount: number | null }; explanation: Explanation; explain: Explain | null; state: SpotState; exploiting: boolean; adjusted?: boolean; opponent_profile: Profile | null }
  | { status: "villain_to_act"; state: SpotState }
  | { status: "need_board"; street: string; cards_needed: number; pot?: number }
  | { status: "hand_complete"; summary: { showdown: boolean; board: string[]; hero_net?: number } };

type RawSpot = {
  hero_cards: string[];
  board: string[];
  hero_position: "button" | "big_blind";
  small_blind: number;
  big_blind: number;
  hero_stack: number;
  villain_stack: number;
  actions: SpotAction[];
  villain_cards: string[] | null;
};

type HandRecord = { id: number; created_at: string; spot: RawSpot; result?: { showdown: boolean; hero_net: number | null } | null };

const ACTION_TEXT: Record<ActionKind, string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise to", all_in: "All-in" };
const STAT_TEXT: Record<string, string> = {
  vpip: "Plays hand (VPIP)", preflop_raise: "Raises preflop", limp: "Limps", three_bet: "3-bets",
  fold_to_raise: "Folds to a raise", aggressive: "Aggression", bet: "Bets when checked to",
  fold_to_bet: "Folds to a bet", call_vs_bet: "Calls a bet", raise_vs_bet: "Raises a bet",
};

const OPPONENT_COUNTS = [1, 2, 3, 4, 5, 6, 7, 8];
const POSTFLOP_STREETS = ["flop", "turn", "river"] as const;
const ACTION_KEYS: Record<string, ActionKind[]> = { F: ["fold"], C: ["check", "call"], B: ["bet", "raise"], A: ["all_in"] };
const KEY_FOR_ACTION: Record<ActionKind, string> = { fold: "F", check: "C", call: "C", bet: "B", raise: "B", all_in: "A" };
const FIELD_LABELS: Record<string, string> = {
  small_blind: "Small blind", big_blind: "Big blind", hero_stack: "Your stack", villain_stack: "Villain stack",
  opponent: "Opponent name", hero_cards: "Your cards", board: "Board", villain_cards: "Villain's cards",
};

function describeError(body: { detail?: unknown } | null, fallback: string): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail) || detail.length === 0) return fallback;
  return detail.map((item: { loc?: (string | number)[]; msg?: string }) => {
    const path = (item.loc ?? []).slice(1);
    const message = (item.msg ?? "invalid value").replace(/^./, (letter) => letter.toLowerCase());
    let label: string;
    if (path[0] === "actions" && typeof path[1] === "number") label = `Action ${path[1] + 1}${path[2] === "amount" ? " amount" : ""}`;
    else label = FIELD_LABELS[String(path[0])] ?? path.join(".");
    return label ? `${label}: ${message}` : message;
  }).join("; ");
}

function describeLabel(label: string): string {
  const [kind, amount] = label.split("_");
  if (label === "all_in") return "All-in";
  if (amount) return `${kind === "bet" ? "Bet" : "Raise to"} ${amount}`;
  return kind[0].toUpperCase() + kind.slice(1);
}

function foldedText(actions: SpotAction[]): string {
  const last = actions[actions.length - 1];
  return last?.action === "fold" ? (last.actor === "hero" ? "You folded." : "Villain folded.") : "Someone folded.";
}

function describeAction(step: SpotAction): string {
  const who = step.actor === "hero" ? "You" : "Villain";
  return `${who}: ${ACTION_TEXT[step.action]}${step.amount ? ` ${step.amount}` : ""}`;
}

function effectiveMaximum(state: SpotState, actor: Actor): number {
  const actorStack = actor === "hero" ? state.hero_stack : state.villain_stack;
  const opponentStack = actor === "hero" ? state.villain_stack : state.hero_stack;
  const actorPosted = state.maximum_target - actorStack;
  const opponentCap = actorPosted + state.to_call + opponentStack;
  return Math.max(state.minimum_target ?? 0, Math.min(state.maximum_target, opponentCap));
}

function quickSizes(state: SpotState, actor: Actor): { label: string; amount: number }[] {
  const { pot, to_call, minimum_target } = state;
  const maximum_target = effectiveMaximum(state, actor);
  const actorStack = actor === "hero" ? state.hero_stack : state.villain_stack;
  const floor = minimum_target ?? 0;
  const currentHighestBet = state.maximum_target - actorStack + to_call;
  const clamp = (raw: number) => Math.min(maximum_target, Math.max(floor, Math.round(raw)));
  const fractions: [string, number][] = [["1/3 pot", 1 / 3], ["1/2 pot", 0.5], ["3/4 pot", 0.75], ["Pot", 1]];
  const sized = fractions.map(([label, fraction]) => ({
    label,
    amount: clamp(to_call > 0 ? currentHighestBet + fraction * (pot + 2 * to_call) : fraction * pot),
  }));
  return [...sized, { label: "All-in", amount: maximum_target }];
}

export default function Coach() {
  const [heroCards, setHeroCards] = useState<string[]>([]);
  const [handNumber, setHandNumber] = useState(0);
  const [logged, setLogged] = useState(false);
  const [position, setPosition] = useState<"button" | "big_blind">("button");
  const [blinds, setBlinds] = useState({ small: "50", big: "100" });
  const [stacks, setStacks] = useState({ hero: "10000", villain: "10000" });
  const [opponent, setOpponent] = useState("");
  const [exploit, setExploit] = useState(true);
  const [board, setBoard] = useState<string[]>([]);
  const [boardDraft, setBoardDraft] = useState<string[]>([]);
  const [actions, setActions] = useState<SpotAction[]>([]);
  const [amount, setAmount] = useState("");
  const [villainCards, setVillainCards] = useState<string[]>([]);
  const [result, setResult] = useState<CoachResponse>();
  const [reviewMode, setReviewMode] = useState(false);
  const [view, setView] = useState<"play" | "review" | "data">("play");
  const [players, setPlayers] = useState(1);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [opponents, setOpponents] = useState<{ name: string; hands: number }[]>([]);
  const [history, setHistory] = useState<HandRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deletingOpponent, setDeletingOpponent] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const spot = useMemo(() => ({
    hero_cards: heroCards, board, hero_position: position,
    small_blind: +blinds.small, big_blind: +blinds.big, hero_stack: +stacks.hero, villain_stack: +stacks.villain, actions,
  }), [heroCards, board, position, blinds, stacks, actions]);

  async function loadOpponents() {
    try {
      const response = await fetch("/api/coach/opponents");
      if (response.ok) setOpponents(await response.json());
    } catch { /* the list is optional */ }
  }

  async function loadProfile(name: string) {
    if (!name.trim()) { setProfile(null); return; }
    try {
      const response = await fetch(`/api/coach/opponents/${encodeURIComponent(name.trim())}`);
      setProfile(response.ok ? (await response.json()).profile : null);
    } catch { setProfile(null); }
  }

  async function loadHistory(name: string) {
    if (!name.trim()) { setHistory([]); return; }
    setHistoryLoading(true); setHistoryError("");
    try {
      const response = await fetch(`/api/coach/opponents/${encodeURIComponent(name.trim())}/hands`);
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load hand history");
      setHistory(body);
    } catch (requestError) {
      setHistory([]);
      setHistoryError(requestError instanceof Error ? requestError.message : "Could not load hand history");
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => { loadOpponents(); }, []);

  async function evaluate(nextActions = actions, nextBoard = board) {
    setError(""); setNotice(""); setLoading(true);
    try {
      const response = await fetch("/api/coach/advise", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...spot, actions: nextActions, board: nextBoard, opponent: opponent.trim() || null, exploit }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(describeError(body, "Coach request failed"));
      setActions(nextActions); setBoard(nextBoard); setResult(body);
      if (body.status === "hero_to_act") setAmount(body.advice.amount ? String(body.advice.amount) : String(body.state.minimum_target ?? ""));
      if (body.status === "villain_to_act") setAmount(String(body.state.minimum_target ?? ""));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Coach request failed");
    } finally {
      setLoading(false);
    }
  }

  function beginHand() {
    setError(""); setBoardDraft([]); setVillainCards([]); setReviewMode(false); setLogged(false);
    loadProfile(opponent); loadHistory(opponent);
    evaluate([], []);
  }

  function start(event: FormEvent) {
    event.preventDefault();
    if (heroCards.length !== 2) { setError("Pick or type exactly two hero cards."); return; }
    beginHand();
  }

  function newHand() {
    setHeroCards([]); setBoard([]); setBoardDraft([]); setVillainCards([]); setActions([]);
    setResult(undefined); setReviewMode(false); setLogged(false); setError(""); setNotice(""); setAmount("");
    setPosition((current) => (current === "button" ? "big_blind" : "button"));
    setHandNumber((current) => current + 1);
  }

  function act(actor: Actor, action: ActionKind) {
    if ((action === "bet" || action === "raise") && state) {
      const total = Number(amount);
      const high = effectiveMaximum(state, actor);
      if (!amount.trim() || !Number.isInteger(total) || total < (state.minimum_target ?? 0) || total > high) {
        setError(`Enter a whole-number total between ${state.minimum_target} and ${high} to ${action}.`);
        return;
      }
    }
    const step: SpotAction = { actor, action, amount: action === "bet" || action === "raise" ? Math.round(+amount) : null };
    evaluate([...actions, step]);
  }

  function undo() {
    if (!actions.length) return;
    const trimmed = actions.slice(0, -1);
    evaluate(trimmed, board);
  }

  function addBoard(event: FormEvent) {
    event.preventDefault();
    if (result?.status !== "need_board") return;
    const needed = result.cards_needed - board.length;
    if (boardDraft.length !== needed) {
      setError(`Enter exactly ${needed} card${needed > 1 ? "s" : ""}.`);
      return;
    }
    evaluate(actions, [...board, ...boardDraft]);
    setBoardDraft([]);
  }

  async function logHand() {
    if (!opponent.trim()) { setError("Enter the opponent's name to log this hand."); return; }
    setError(""); setLoading(true);
    try {
      const response = await fetch("/api/coach/hands", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...spot, opponent: opponent.trim(), villain_cards: villainCards.length === 2 ? villainCards : null }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(describeError(body, "Could not log the hand"));
      setLogged(true);
      setProfile(body.opponent_profile); setNotice(`Logged. ${opponent.trim()} now has ${body.opponent_profile.hands_observed} ${body.opponent_profile.hands_observed === 1 ? "hand" : "hands"} on record.`);
      loadOpponents(); loadHistory(opponent);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not log the hand");
    } finally {
      setLoading(false);
    }
  }

  async function viewHand(record: HandRecord) {
    setHistoryError(""); setLoading(true);
    try {
      const response = await fetch("/api/coach/advise", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...record.spot, opponent: null, exploit: false }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error("Could not load this hand");
      setHeroCards(record.spot.hero_cards);
      setBoard(record.spot.board);
      setActions(record.spot.actions);
      setVillainCards(record.spot.villain_cards ?? []);
      setStacks({ hero: String(record.spot.hero_stack), villain: String(record.spot.villain_stack) });
      setBlinds({ small: String(record.spot.small_blind), big: String(record.spot.big_blind) });
      setPosition(record.spot.hero_position);
      setResult(body); setReviewMode(true); setLogged(false); setError(""); setNotice("");
    } catch (requestError) {
      setHistoryError(requestError instanceof Error ? requestError.message : "Could not load this hand");
    } finally {
      setLoading(false);
    }
  }

  async function deleteHand(id: number) {
    if (!window.confirm("Delete this hand? This cannot be undone.")) return;
    setDeletingId(id); setHistoryError("");
    try {
      const response = await fetch(`/api/coach/hands/${id}`, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Could not delete this hand");
      }
      setHistory((current) => current.filter((record) => record.id !== id));
      loadOpponents();
      if (opponent.trim()) loadProfile(opponent);
    } catch (requestError) {
      setHistoryError(requestError instanceof Error ? requestError.message : "Could not delete this hand");
    } finally {
      setDeletingId(null);
    }
  }

  async function deleteOpponentHands() {
    const name = opponent.trim();
    if (!name) return;
    if (!window.confirm(`Delete all logged hands for ${name}? This cannot be undone.`)) return;
    setDeletingOpponent(true); setHistoryError("");
    try {
      const response = await fetch(`/api/coach/opponents/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Could not delete this opponent");
      }
      setHistory([]); setProfile(null); setNotice(`Deleted all hands for ${name}.`);
      loadOpponents();
    } catch (requestError) {
      setHistoryError(requestError instanceof Error ? requestError.message : "Could not delete this opponent");
    } finally {
      setDeletingOpponent(false);
    }
  }

  const state = result && "state" in result ? result.state : undefined;
  const usedForHero = new Set([...board, ...boardDraft, ...villainCards]);
  const usedForBoard = new Set([...heroCards, ...villainCards, ...board]);
  const usedForVillain = new Set([...heroCards, ...board]);

  useEffect(() => {
    if (!result || (result.status !== "hero_to_act" && result.status !== "villain_to_act") || loading) return;
    const actor: Actor = result.status === "hero_to_act" ? "hero" : "villain";
    const legal = result.state.legal_actions;
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)) return;
      const choice = ACTION_KEYS[event.key.toUpperCase()]?.find((candidate) => legal.includes(candidate));
      if (!choice) return;
      event.preventDefault();
      act(actor, choice);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function actionButtons(actor: Actor) {
    if (!state) return null;
    const sized = state.legal_actions.some((a) => a === "bet" || a === "raise");
    return (
      <div className="coach-actions">
        {sized && (
          <div className="coach-size-row">
            <label className="coach-amount">Total this street
              <input
                inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  e.preventDefault();
                  const sizedAction = state.legal_actions.find((a) => a === "bet" || a === "raise");
                  if (sizedAction && !loading) act(actor, sizedAction);
                }}
              />
              <small>{state.minimum_target} – {effectiveMaximum(state, actor)}</small>
            </label>
            <div className="coach-quick-sizes" role="group" aria-label="Quick bet sizes">
              {quickSizes(state, actor).map((size) => (
                <button key={size.label} type="button" className="chip" disabled={loading} onClick={() => setAmount(String(size.amount))}>
                  {size.label}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="coach-action-row">
        {state.legal_actions.map((action) => (
          <button key={action} type="button" className="secondary" disabled={loading} title={`Shortcut: ${KEY_FOR_ACTION[action]}`} onClick={() => act(actor, action)}>
            {ACTION_TEXT[action]}{(action === "bet" || action === "raise") && amount ? ` ${amount}` : ""}{action === "call" ? ` ${state.to_call}` : ""}
            <span className="key-hint" aria-hidden="true">{KEY_FOR_ACTION[action]}</span>
          </button>
        ))}
        </div>
      </div>
    );
  }

  const opponentRow = (
    <div className="opponent-count" role="radiogroup" aria-label="Opponents in the hand">
      <span className="field-label">Opponents</span>
      <div className="segmented">
        {OPPONENT_COUNTS.map((count) => (
          <button
            key={count} type="button" role="radio" aria-checked={players === count}
            className={players === count ? "is-on" : ""}
            onClick={() => setPlayers(count)} disabled={!!result && count !== players}
          >
            {count}
          </button>
        ))}
      </div>
      <small className="muted">{players === 1 ? "Heads-up: solver advice and opponent learning" : `${players}-way pot: equity and pot-odds advice`}</small>
    </div>
  );

  return (
    <section className="coach-panel">
      <div className="coach-head">
        <h2>Coach</h2>
        <div className="segmented" role="tablist" aria-label="Coach view">
          {([["play", "Play a hand"], ["review", "Review"], ["data", "Saved data"]] as const).map(([key, text]) => (
            <button key={key} type="button" role="tab" aria-selected={view === key} className={view === key ? "is-on" : ""} onClick={() => { setView(key); if (key !== "play") loadOpponents(); }}>{text}</button>
          ))}
        </div>
      </div>

      {view === "review" ? <CoachReview opponents={opponents} /> : view === "data" ? <CoachData opponents={opponents} onChanged={() => { loadOpponents(); if (opponent.trim()) { loadProfile(opponent); loadHistory(opponent); } }} /> : (<>
      {opponentRow}
      {players > 1 ? <CoachMultiway key={players} opponents={players} /> : (<>
      {!result ? (
      <form onSubmit={start} className="coach-setup">
        <CardInput key={handNumber} label="Your cards" slots={["Card 1", "Card 2"]} cards={heroCards} onChange={setHeroCards} usedCards={usedForHero} />
        <div className="setup-row">
          <div className="field">
            <span className="field-label" id="position-label">Your position</span>
            <div className="segmented" role="radiogroup" aria-labelledby="position-label">
              {([["button", "Button / SB"], ["big_blind", "Big blind"]] as const).map(([key, text]) => (
                <button key={key} type="button" role="radio" aria-checked={position === key} className={position === key ? "is-on" : ""} onClick={() => setPosition(key)}>{text}</button>
              ))}
            </div>
          </div>
          <label>Small blind<input inputMode="numeric" value={blinds.small} onChange={(e) => setBlinds({ ...blinds, small: e.target.value })} /></label>
          <label>Big blind<input inputMode="numeric" value={blinds.big} onChange={(e) => setBlinds({ ...blinds, big: e.target.value })} /></label>
          <label>Your stack<input inputMode="numeric" value={stacks.hero} onChange={(e) => setStacks({ ...stacks, hero: e.target.value })} /></label>
          <label>Their stack<input inputMode="numeric" value={stacks.villain} onChange={(e) => setStacks({ ...stacks, villain: e.target.value })} /></label>
        </div>
        <div className="setup-row">
          <label className="field-grow">Opponent name <span className="muted">(optional, so the Coach learns their style)</span><input list="coach-opponents" value={opponent} onChange={(e) => setOpponent(e.target.value)} placeholder="e.g. Alex" />
            <datalist id="coach-opponents">{opponents.map((o) => <option key={o.name} value={o.name}>{o.hands} hands</option>)}</datalist>
          </label>
          <label className="coach-toggle"><input type="checkbox" checked={exploit} onChange={(e) => setExploit(e.target.checked)} />Adjust advice to this opponent</label>
        </div>
        <div className="coach-form-actions">
          <button className="primary" disabled={loading || heroCards.length !== 2}>{loading ? "Thinking…" : heroCards.length === 2 ? "Start hand" : `Pick ${2 - heroCards.length} more card${heroCards.length === 1 ? "" : "s"}`}</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
      ) : (
        <div className="hand-bar">
          <div className="hand-bar-cards">{heroCards.map((card) => <PlayingCard key={card} card={card} />)}</div>
          <span>{position === "button" ? "Button / SB" : "Big blind"} · {blinds.small}/{blinds.big} · stacks {stacks.hero} vs {stacks.villain}{opponent.trim() ? ` · vs ${opponent.trim()}` : ""}</span>
          {reviewMode && <span className="pill">Reviewing a logged hand</span>}
          <button type="button" className="secondary" onClick={newHand} disabled={loading}>New hand</button>
        </div>
      )}

      {notice && <p className="coach-notice" role="status">{notice}</p>}

      {result && (
        <div className="coach-layout">
          <div className="coach-main">
            <div className="coach-table">
              <div><span className="field-label">Board</span><div className="board-cards">{board.length ? board.map((c) => <PlayingCard key={c} card={c} />) : <span className="muted">Preflop</span>}</div></div>
              {state && <div><span className="field-label">Pot</span><strong>{state.pot}</strong>{state.to_call > 0 && <span className="muted"> · to call {state.to_call}</span>}</div>}
              {result.status === "need_board" && result.pot !== undefined && <div><span className="field-label">Pot</span><strong>{result.pot}</strong></div>}
            </div>

            {actions.length > 0 && (
              <ol className="coach-log">
                {actions.map((step, index) => <li key={index}>{describeAction(step)}</li>)}
              </ol>
            )}
            {!reviewMode && actions.length > 0 && <button type="button" className="link-button" onClick={undo} disabled={loading}>Undo last action</button>}

            {error && <p className="error" role="alert">{error}</p>}

            {result.status === "villain_to_act" && (<div className="coach-step"><h3>{opponent.trim() || "Opponent"} to act</h3><p className="muted">What did they do?</p>{actionButtons("villain")}</div>)}

            {result.status === "need_board" && (() => {
              const needed = result.cards_needed - board.length;
              const slotName = result.street[0].toUpperCase() + result.street.slice(1);
              return (
                <form onSubmit={addBoard} className="coach-step">
                  <CardInput
                    key={`${result.street}-${board.length}`}
                    label={`Deal the ${result.street}`}
                    slots={Array(needed).fill(slotName)}
                    cards={boardDraft} onChange={setBoardDraft} usedCards={usedForBoard}
                  />
                  <button className="primary" disabled={loading || boardDraft.length !== needed}>{boardDraft.length === needed ? `Add ${result.street}` : `Pick ${needed - boardDraft.length} more`}</button>
                </form>
              );
            })()}

            {result.status === "hero_to_act" && (
              <div className="coach-advice">
                <h3 className="coach-recommendation">Recommended: {ACTION_TEXT[result.advice.action]}{result.advice.amount ? ` ${result.advice.amount}` : ""}</h3>
                {result.explain?.reason && <p className="coach-reason">{result.explain.reason}</p>}
                {result.explain && <CoachStrategy options={result.explain.options} />}
                {result.explain?.ev_note && <p className="muted"><small>{result.explain.ev_note}</small></p>}
                {result.explanation.source !== "fallback" && (
                  <p className="muted">Mixed strategy from {result.explanation.source === "postflop_solve" ? "a real-time solve of this street" : result.explanation.source === "preflop_exploit" ? "the preflop chart re-solved for this opponent" : "the preflop chart"}.
                    {(result.adjusted ?? result.exploiting) ? " Adjusted to this opponent's tendencies." : ""}</p>
                )}
                {result.explanation.hero_equity_vs_range !== undefined && (
                  <p>Your equity vs their estimated range: <strong>{Math.round(result.explanation.hero_equity_vs_range * 100)}%</strong></p>
                )}
                {result.explanation.villain_range_makeup && (
                  <p className="coach-range"><small>THEIR ESTIMATED RANGE</small><br />{result.explanation.villain_range_makeup.filter((item) => item.share >= 0.01).map((item) => `${Math.round(item.share * 100)}% ${item.type}`).join(" · ")}</p>
                )}
                {result.explanation.villain_top_classes && (
                  <p className="coach-range"><small>MOST LIKELY VILLAIN HANDS</small><br />{result.explanation.villain_top_classes.slice(0, 10).map((item) => `${item.hand} ${Math.round(item.share * 100)}%`).join(" · ")}</p>
                )}
                <h3>What did you do?</h3>
                {actionButtons("hero")}
              </div>
            )}

            {result.status === "hand_complete" && (
              <div className="coach-advice">
                <h3>Hand complete</h3>
                <p>{result.summary.showdown ? "Showdown." : foldedText(actions)} {result.summary.hero_net !== undefined && <strong className={result.summary.hero_net >= 0 ? "positive" : "negative"}>{result.summary.hero_net >= 0 ? "+" : ""}{result.summary.hero_net}</strong>}</p>
                {reviewMode ? (
                  <p className="muted">Loaded from hand history for review. Start or press "New hand" to enter a new one.</p>
                ) : (
                  <>
                    {result.summary.showdown && (
                      <CardInput label="Their shown cards (optional)" slots={["Card 1", "Card 2"]} cards={villainCards} onChange={setVillainCards} usedCards={usedForVillain} />
                    )}
                    <button type="button" className="primary" onClick={logHand} disabled={loading || logged || !opponent.trim()}>{logged ? "Hand logged" : opponent.trim() ? `Log hand vs ${opponent.trim()}` : "Enter an opponent name to log"}</button>
                  </>
                )}
              </div>
            )}
          </div>

          <aside className="coach-profile">
            <div className="coach-panel-header">
              <h3>{opponent.trim() || "Opponent"}</h3>
              {opponent.trim() && (profile || history.length > 0) && (
                <button type="button" className="secondary danger" onClick={deleteOpponentHands} disabled={deletingOpponent}>
                  {deletingOpponent ? "Deleting..." : "Delete opponent"}
                </button>
              )}
            </div>
            {profile ? (
              <>
                <p><strong>{profile.classification.replace(/_/g, " ")}</strong> · {profile.hands_observed} {profile.hands_observed === 1 ? "hand" : "hands"}
                  {profile.label && <small className="muted"> · {profile.label.assigned ? `${profile.label.confidence.replace("_", " ")} confidence, based on ${profile.label.decisions} decisions` : "no label yet (needs 20+ hands)"}</small>}</p>
                <ul>
                  {Object.entries(profile.preflop).filter(([, read]) => read.opportunities > 0).map(([name, read]) => (
                    <li key={name}><span>{STAT_TEXT[name] ?? name}</span><b>{Math.round(read.frequency * 100)}%</b><small>{read.confidence.replace("_", " ")} ({read.opportunities})</small></li>
                  ))}
                  {POSTFLOP_STREETS.flatMap((street) => Object.entries(profile.postflop[street] ?? {})
                    .filter(([, read]) => read.opportunities > 0)
                    .map(([name, read]) => (
                      <li key={`${street}-${name}`}><span>{street[0].toUpperCase() + street.slice(1)}: {STAT_TEXT[name] ?? name}</span><b>{Math.round(read.frequency * 100)}%</b><small>{read.confidence.replace("_", " ")} ({read.opportunities})</small></li>
                    )))}
                </ul>
                <p className="muted">Reads need roughly 20+ opportunities before they carry weight.</p>
              </>
            ) : opponent.trim() ? <p className="muted">No logged hands yet. Log finished hands to build a profile.</p> : <p className="muted">Enter an opponent's name to track them.</p>}

            {opponent.trim() && (
              <div className="coach-history">
                <h4>Hand history</h4>
                {historyLoading && <p className="muted">Loading...</p>}
                {historyError && <p className="error" role="alert">{historyError}</p>}
                {!historyLoading && history.length === 0 && !historyError && <p className="muted">No hands logged yet.</p>}
                {history.length > 0 && (
                  <ul>
                    {history.map((record) => (
                      <li key={record.id}>
                        <button type="button" className="coach-history-entry" onClick={() => viewHand(record)} disabled={loading}>
                          <span className="coach-history-meta">
                            <span>{record.spot.hero_cards.join(" ")}{record.spot.board.length > 0 && ` · ${record.spot.board.join(" ")}`}</span>
                            <small>
                              {record.spot.actions.length > 0 && `${describeAction(record.spot.actions[record.spot.actions.length - 1])} · `}
                              {record.result?.hero_net != null && <><strong className={record.result.hero_net >= 0 ? "positive" : "negative"}>{record.result.hero_net >= 0 ? "+" : ""}{record.result.hero_net}</strong> · </>}
                              {new Date(record.created_at).toLocaleString()}
                            </small>
                          </span>
                        </button>
                        <button type="button" className="secondary danger" onClick={() => deleteHand(record.id)} disabled={deletingId === record.id}>
                          {deletingId === record.id ? "..." : "Delete"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </aside>
        </div>
      )}
      </>)}
      </>)}
    </section>
  );
}
