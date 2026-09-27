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

const ACTION_TEXT: Record<ActionKind, string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise to", all_in: "All-in" };
const STAT_TEXT: Record<string, string> = {
  vpip: "Plays hand (VPIP)", preflop_raise: "Raises preflop", limp: "Limps", three_bet: "3-bets",
  fold_to_raise: "Folds to a raise", aggressive: "Aggression", bet: "Bets when checked to",
  fold_to_bet: "Folds to a bet", call_vs_bet: "Calls a bet", raise_vs_bet: "Raises a bet",
};

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

export default function Coach() {
  const [heroCards, setHeroCards] = useState("As Kd");
  const [position, setPosition] = useState<"button" | "big_blind">("button");
  const [blinds, setBlinds] = useState({ small: "50", big: "100" });
  const [stacks, setStacks] = useState({ hero: "10000", villain: "10000" });
  const [opponent, setOpponent] = useState("");
  const [exploit, setExploit] = useState(true);
  const [board, setBoard] = useState<string[]>([]);
  const [actions, setActions] = useState<SpotAction[]>([]);
  const [boardInput, setBoardInput] = useState("");
  const [amount, setAmount] = useState("");
  const [villainCards, setVillainCards] = useState("");
  const [result, setResult] = useState<CoachResponse>();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [opponents, setOpponents] = useState<{ name: string; hands: number }[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const spot = useMemo(() => ({
    hero_cards: parseCards(heroCards), board, hero_position: position,
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

  function start(event: FormEvent) {
    event.preventDefault();
    setBoardInput(""); setVillainCards("");
    loadProfile(opponent);
    evaluate([], []);
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
    evaluate(actions, [...board, ...parseCards(boardInput)]);
    setBoardInput("");
  }

  async function logHand() {
    if (!opponent.trim()) { setError("Enter the opponent's name to log this hand."); return; }
    setError(""); setLoading(true);
    try {
      const shown = parseCards(villainCards);
      const response = await fetch("/api/coach/hands", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...spot, opponent: opponent.trim(), villain_cards: shown.length === 2 ? shown : null }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || "Could not log the hand");
      setProfile(body.opponent_profile); setNotice(`Logged. ${opponent.trim()} now has ${body.opponent_profile.hands_observed} hands on record.`);
      loadOpponents();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not log the hand");
    } finally {
      setLoading(false);
    }
  }

  const state = result && "state" in result ? result.state : undefined;

  function actionButtons(actor: Actor) {
    if (!state) return null;
    const sized = state.legal_actions.some((a) => a === "bet" || a === "raise");
    return (
      <div className="coach-actions">
        {sized && (
          <label className="coach-amount">Total this street
            <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <small>{state.minimum_target} – {state.maximum_target}</small>
          </label>
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
          <label>Your cards<input value={heroCards} onChange={(e) => setHeroCards(e.target.value)} placeholder="As Kd" /></label>
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
        <button className="analyze" disabled={loading}>{loading ? "Thinking..." : "Start hand"}</button>
      </form>

      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="coach-notice" role="status">{notice}</p>}

      {result && (
        <div className="coach-layout">
          <div className="coach-main">
            <div className="coach-table">
              <p><small>BOARD</small><br />{board.length ? board.map((c) => <span key={c} className={`card-token ${"hd".includes(c[1]) ? "red" : ""}`}>{c}</span>) : <span className="muted">No board yet</span>}</p>
              {state && <p><small>POT</small><br /><strong>{state.pot}</strong>{state.to_call > 0 && <span className="muted"> · to call {state.to_call}</span>}</p>}
            </div>

            <ol className="coach-log">
              {actions.map((step, index) => <li key={index}>{describeAction(step)}</li>)}
            </ol>
            {actions.length > 0 && <button type="button" className="secondary" onClick={undo} disabled={loading}>Undo last action</button>}

            {result.status === "villain_to_act" && (<><h3>Villain to act</h3><p className="muted">Enter what the opponent did.</p>{actionButtons("villain")}</>)}

            {result.status === "need_board" && (
              <form onSubmit={addBoard} className="coach-board">
                <label>Enter the {result.street} ({result.street === "flop" ? "3 cards" : "1 card"})<input value={boardInput} onChange={(e) => setBoardInput(e.target.value)} placeholder={result.street === "flop" ? "Ah 7c 2d" : "Ts"} autoFocus /></label>
                <button className="secondary" disabled={loading}>Add {result.street}</button>
              </form>
            )}

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
                {result.summary.showdown && (
                  <label>Villain's shown cards (optional)<input value={villainCards} onChange={(e) => setVillainCards(e.target.value)} placeholder="Qh Qd" /></label>
                )}
                <button type="button" className="analyze" onClick={logHand} disabled={loading || !opponent.trim()}>{opponent.trim() ? `Log hand vs ${opponent.trim()}` : "Enter an opponent name to log"}</button>
              </div>
            )}
          </div>

          <aside className="coach-profile">
            <h3>{opponent.trim() || "Opponent"}</h3>
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
            ) : <p className="muted">No logged hands yet. Log finished hands to build a profile.</p>}
          </aside>
        </div>
      )}
    </section>
  );
}
