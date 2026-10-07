import { FormEvent, useEffect, useMemo, useState } from "react";

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
  labels: string[];
  probabilities: number[];
  chosen: string;
  hero_equity_vs_range?: number;
  villain_effective_combos?: number;
  villain_top_classes?: { hand: string; share: number }[];
  villain_range_makeup?: { type: string; share: number }[];
  exploit?: { active: boolean; hands_observed?: number; classification?: string; locked_nodes?: number };
  reason?: string;
};

type StatRead = { frequency: number; opportunities: number; confidence: string };
type Profile = {
  hands_observed: number;
  classification: string;
  preflop: Record<string, StatRead>;
  postflop: Record<string, Record<string, StatRead>>;
};

type CoachResponse =
  | { status: "hero_to_act"; advice: { action: ActionKind; amount: number | null }; explanation: Explanation; state: SpotState; exploiting: boolean; opponent_profile: Profile | null }
  | { status: "villain_to_act"; state: SpotState }
  | { status: "need_board"; street: string; cards_needed: number }
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

type HandRecord = { id: number; created_at: string; spot: RawSpot };

const ACTION_TEXT: Record<ActionKind, string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise to", all_in: "All-in" };
const STAT_TEXT: Record<string, string> = {
  vpip: "Plays hand (VPIP)", preflop_raise: "Raises preflop", limp: "Limps", three_bet: "3-bets",
  fold_to_raise: "Folds to a raise", aggressive: "Aggression", bet: "Bets when checked to",
  fold_to_bet: "Folds to a bet", call_vs_bet: "Calls a bet", raise_vs_bet: "Raises a bet",
};

const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SUITS = ["s", "h", "d", "c"] as const;
const SUIT_SYMBOL: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };
const SUIT_NAME: Record<string, string> = { s: "spades", h: "hearts", d: "diamonds", c: "clubs" };
const RANK_NAME: Record<string, string> = {
  A: "ace", K: "king", Q: "queen", J: "jack", T: "ten", "9": "nine", "8": "eight",
  "7": "seven", "6": "six", "5": "five", "4": "four", "3": "three", "2": "two",
};
const RED_SUITS = new Set(["h", "d"]);

function parseCards(text: string): string[] {
  return text.split(/[\s,]+/).filter(Boolean).map((card) => card.length === 2 ? card[0].toUpperCase() + card[1].toLowerCase() : card);
}

function describeLabel(label: string): string {
  const [kind, amount] = label.split("_");
  if (label === "all_in") return "All-in";
  if (amount) return `${kind === "bet" ? "Bet" : "Raise to"} ${amount}`;
  return kind[0].toUpperCase() + kind.slice(1);
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

function CardPicker({ selected, onToggle, disabled, max }: { selected: string[]; onToggle: (card: string) => void; disabled: Set<string>; max: number }) {
  return (
    <div className="card-picker" role="group" aria-label="Card picker">
      {RANKS.map((rank) => SUITS.map((suit) => {
        const card = rank + suit;
        const isSelected = selected.includes(card);
        const isDisabled = !isSelected && (disabled.has(card) || selected.length >= max);
        return (
          <button
            key={card} type="button"
            className={`card-cell${RED_SUITS.has(suit) ? " red" : ""}${isSelected ? " selected" : ""}`}
            aria-pressed={isSelected} aria-label={`${RANK_NAME[rank]} of ${SUIT_NAME[suit]}`}
            disabled={isDisabled} onClick={() => onToggle(card)}
          >
            {rank}{SUIT_SYMBOL[suit]}
          </button>
        );
      }))}
    </div>
  );
}

function CardField({ label, cards, onChange, max, usedCards, placeholder, autoFocus }: {
  label: string; cards: string[]; onChange: (cards: string[]) => void; max: number; usedCards: Set<string>; placeholder?: string; autoFocus?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(cards.join(" "));
  const joined = cards.join(" ");
  useEffect(() => { setText(joined); }, [joined]);

  function commitText(value: string) {
    setText(value);
    onChange(parseCards(value).slice(0, max));
  }

  function toggle(card: string) {
    if (cards.includes(card)) onChange(cards.filter((c) => c !== card));
    else if (cards.length < max) onChange([...cards, card]);
  }

  return (
    <div className="card-field">
      <label>{label}
        <div className="card-field-row">
          <input value={text} onChange={(e) => commitText(e.target.value)} placeholder={placeholder} autoFocus={autoFocus} />
          <button type="button" className="secondary card-field-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? "Hide" : "Pick"}
          </button>
        </div>
      </label>
      {open && <CardPicker selected={cards} onToggle={toggle} disabled={usedCards} max={max} />}
    </div>
  );
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
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || "Coach request failed");
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
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || "Could not log the hand");
      setLogged(true);
      setProfile(body.opponent_profile); setNotice(`Logged. ${opponent.trim()} now has ${body.opponent_profile.hands_observed} hands on record.`);
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

  function actionButtons(actor: Actor) {
    if (!state) return null;
    const sized = state.legal_actions.some((a) => a === "bet" || a === "raise");
    return (
      <div className="coach-actions">
        {sized && (
          <>
            <label className="coach-amount">Total this street
              <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} />
              <small>{state.minimum_target} – {effectiveMaximum(state, actor)}</small>
            </label>
            <div className="coach-quick-sizes" role="group" aria-label="Quick bet sizes">
              {quickSizes(state, actor).map((size) => (
                <button key={size.label} type="button" className="chip" disabled={loading} onClick={() => setAmount(String(size.amount))}>
                  {size.label}
                </button>
              ))}
            </div>
          </>
        )}
        {state.legal_actions.map((action) => (
          <button key={action} type="button" className="secondary" disabled={loading} onClick={() => act(actor, action)}>
            {ACTION_TEXT[action]}{(action === "bet" || action === "raise") && amount ? ` ${amount}` : ""}{action === "call" ? ` ${state.to_call}` : ""}
          </button>
        ))}
      </div>
    );
  }

  return (
    <section className="match-panel coach-panel">
      <h2>Coach</h2>
      <p>Enter your hand and the action as it happens. When it is your turn, the solver recommends a play; log finished hands under the opponent's name so the Coach learns their style.</p>
      <p className="muted">Heads-up only. Manual entry for study, review, and practice. Real-time assistance while playing on a poker site breaks most sites' rules.</p>

      <form onSubmit={start}>
        <div className="form-grid">
          <div className="span-2">
            <CardField key={handNumber} label="Your cards" cards={heroCards} onChange={setHeroCards} max={2} usedCards={usedForHero} placeholder="As Kd" autoFocus={handNumber > 0} />
          </div>
          <label>Your position<select value={position} onChange={(e) => setPosition(e.target.value as "button" | "big_blind")}><option value="button">Button (small blind)</option><option value="big_blind">Big blind</option></select></label>
          <label>Small blind<input inputMode="numeric" value={blinds.small} onChange={(e) => setBlinds({ ...blinds, small: e.target.value })} /></label>
          <label>Big blind<input inputMode="numeric" value={blinds.big} onChange={(e) => setBlinds({ ...blinds, big: e.target.value })} /></label>
          <label>Your stack<input inputMode="numeric" value={stacks.hero} onChange={(e) => setStacks({ ...stacks, hero: e.target.value })} /></label>
          <label>Villain stack<input inputMode="numeric" value={stacks.villain} onChange={(e) => setStacks({ ...stacks, villain: e.target.value })} /></label>
          <label>Opponent (optional)<input list="coach-opponents" value={opponent} onChange={(e) => setOpponent(e.target.value)} placeholder="Name to track" />
            <datalist id="coach-opponents">{opponents.map((o) => <option key={o.name} value={o.name}>{o.hands} hands</option>)}</datalist>
          </label>
          <label className="coach-toggle"><input type="checkbox" checked={exploit} onChange={(e) => setExploit(e.target.checked)} />Adjust to this opponent</label>
        </div>
        <div className="coach-form-actions">
          <button className="analyze" disabled={loading}>{loading ? "Thinking..." : "Start hand"}</button>
          {result && <button type="button" className="secondary" onClick={newHand} disabled={loading}>New hand</button>}
        </div>
        {!result && error && <p className="error" role="alert">{error}</p>}
      </form>

      {notice && <p className="coach-notice" role="status">{notice}</p>}

      {result && (
        <div className="coach-layout">
          <div className="coach-main">
            <div className="coach-table">
              <p><small>BOARD</small><br />{board.length ? board.map((c) => <span key={c} className={`card-token ${"hd".includes(c[1]) ? "red" : ""}`}>{c}</span>) : <span className="muted">No board yet</span>}</p>
              {state && <p><small>POT</small><br /><strong>{state.pot}</strong>{state.to_call > 0 && <span className="muted"> · to call {state.to_call}</span>}</p>}
              {reviewMode && <p className="muted eyebrow">REVIEWING A LOGGED HAND</p>}
            </div>

            <ol className="coach-log">
              {actions.map((step, index) => <li key={index}>{describeAction(step)}</li>)}
            </ol>
            {!reviewMode && actions.length > 0 && <button type="button" className="secondary" onClick={undo} disabled={loading}>Undo last action</button>}

            {error && <p className="error" role="alert">{error}</p>}

            {result.status === "villain_to_act" && (<><h3>Villain to act</h3><p className="muted">Enter what the opponent did.</p>{actionButtons("villain")}</>)}

            {result.status === "need_board" && (() => {
              const needed = result.cards_needed - board.length;
              return (
                <form onSubmit={addBoard} className="coach-board">
                  <CardField
                    label={`Enter the ${result.street} (${needed} card${needed > 1 ? "s" : ""})`}
                    cards={boardDraft} onChange={setBoardDraft} max={needed} usedCards={usedForBoard}
                    placeholder={result.street === "flop" ? "Ah 7c 2d" : "Ts"} autoFocus
                  />
                  <button className="secondary" disabled={loading}>Add {result.street}</button>
                </form>
              );
            })()}

            {result.status === "hero_to_act" && (
              <div className="coach-advice">
                <p className="eyebrow">RECOMMENDED</p>
                <p className="coach-recommendation">{ACTION_TEXT[result.advice.action]}{result.advice.amount ? ` ${result.advice.amount}` : ""}</p>
                <div className="coach-strategy">
                  {result.explanation.labels.map((label, index) => (
                    <div key={label} className="coach-bar">
                      <span>{describeLabel(label)}</span>
                      <div><i style={{ width: `${Math.round(result.explanation.probabilities[index] * 100)}%` }} /></div>
                      <b>{Math.round(result.explanation.probabilities[index] * 100)}%</b>
                    </div>
                  ))}
                </div>
                <p className="muted">Mixed strategy from {result.explanation.source === "postflop_solve" ? "a real-time solve of this street" : result.explanation.source === "preflop_exploit" ? "the preflop chart re-solved for this opponent" : result.explanation.source === "preflop_chart" ? "the preflop chart" : "the fallback rule bot"}.
                  {result.exploiting ? " Adjusted to this opponent's tendencies." : ""}</p>
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
                <p>{result.summary.showdown ? "Showdown." : "Someone folded."} {result.summary.hero_net !== undefined && <strong className={result.summary.hero_net >= 0 ? "positive" : "negative"}>{result.summary.hero_net >= 0 ? "+" : ""}{result.summary.hero_net}</strong>}</p>
                {reviewMode ? (
                  <p className="muted">Loaded from hand history for review. Start or press "New hand" to enter a new one.</p>
                ) : (
                  <>
                    {result.summary.showdown && (
                      <CardField label="Villain's shown cards (optional)" cards={villainCards} onChange={setVillainCards} max={2} usedCards={usedForVillain} placeholder="Qh Qd" />
                    )}
                    <button type="button" className="analyze" onClick={logHand} disabled={loading || logged || !opponent.trim()}>{logged ? "Hand logged" : opponent.trim() ? `Log hand vs ${opponent.trim()}` : "Enter an opponent name to log"}</button>
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
                <p><strong>{profile.classification.replace(/_/g, " ")}</strong> · {profile.hands_observed} hands</p>
                <ul>
                  {Object.entries(profile.preflop).map(([name, read]) => (
                    <li key={name}><span>{STAT_TEXT[name] ?? name}</span><b>{Math.round(read.frequency * 100)}%</b><small>{read.confidence.replace("_", " ")}</small></li>
                  ))}
                  {Object.entries(profile.postflop.flop ?? {}).map(([name, read]) => (
                    <li key={name}><span>Flop: {STAT_TEXT[name] ?? name}</span><b>{Math.round(read.frequency * 100)}%</b><small>{read.confidence.replace("_", " ")}</small></li>
                  ))}
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
    </section>
  );
}
