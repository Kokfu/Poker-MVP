import { FormEvent, useEffect, useLayoutEffect, useState } from "react";
import { CardInput, isTypingTarget } from "./CardInput";

type MultiwayAdvice = {
  opponents: number;
  equity: number;
  win_rate: number;
  tie_rate: number;
  fair_share: number;
  required_equity: number;
  action: "fold" | "check" | "call" | "bet" | "raise";
  reason: string;
  hand_label: string;
  draws: { type: string }[];
  note: string;
  opponent_ranges?: { seat: number; effective_combos: number }[];
};

const ACTION_TEXT: Record<MultiwayAdvice["action"], string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise" };
const BOARD_SLOTS = ["Flop", "Flop", "Flop", "Turn", "River"];
const STREETS = { preflop: 0, flop: 3, turn: 4, river: 5 } as const;
const PUBLIC_ACTIONS = { check: "Check", call: "Call", limp: "Limp", bet: "Bet", raise: "Raise", "3-bet": "3-bet", all_in: "All-in" } as const;
type Street = keyof typeof STREETS;
type PublicAction = { seat: number; street: Street; action: keyof typeof PUBLIC_ACTIONS; pot_fraction?: number };
const pct = (value: number) => `${Math.round(value * 100)}%`;

/** Equity-and-pot-odds advice for pots with two or more opponents. */
export default function CoachMultiway({ opponents }: { opponents: number }) {
  const [heroCards, setHeroCards] = useState<string[]>([]);
  const [board, setBoard] = useState<string[]>([]);
  const [pot, setPot] = useState("150");
  const [toCall, setToCall] = useState("100");
  const [advice, setAdvice] = useState<MultiwayAdvice>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [useRanges, setUseRanges] = useState(false);
  const [actions, setActions] = useState<PublicAction[]>([]);
  const [newAction, setNewAction] = useState<PublicAction>({ seat: 1, street: "preflop", action: "raise" });
  const [fraction, setFraction] = useState("");

  const boardOpen = heroCards.length === 2 ? (board.length >= 3 ? Math.min(5, board.length + 1) : 3) : 0;
  const latestStreet = actions.at(-1)?.street ?? "preflop";
  const streets = (Object.keys(STREETS) as Street[]).filter(street =>
    STREETS[street] <= board.length && STREETS[street] >= STREETS[latestStreet]);
  const street = streets.includes(newAction.street) ? newAction.street : streets[0];
  const validFraction = fraction === "" || (Number(fraction) >= 0 && Number(fraction) <= 100);

  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/coach/multiway/settings", { signal: abort.signal }).then(response =>
      response.ok ? response.json() : null
    ).then(settings => {
      if (!abort.signal.aborted) setUseRanges(settings?.opponent_actions === true);
    }).catch(() => {});
    return () => abort.abort();
  }, []);

  // Enter anywhere (outside a text field or button) asks for advice, so typed cards need no mouse at all.
  useLayoutEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Enter" || event.defaultPrevented || isTypingTarget(event.target)) return;
      if ((event.target as HTMLElement | null)?.tagName === "BUTTON" || loading || heroCards.length !== 2) return;
      event.preventDefault();
      submit();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    setError("");
    if (heroCards.length !== 2) { setError("Pick your two cards first."); return; }
    if (![0, 3, 4, 5].includes(board.length)) { setError("The board needs 0, 3, 4 or 5 cards. Finish the flop or clear it."); return; }
    setLoading(true);
    try {
      const response = await fetch("/api/coach/multiway", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hero_cards: heroCards, board, opponents, pot: Number(pot) || 0, to_call: Number(toCall) || 0,
          ...(useRanges && actions.length ? { actions } : {}) }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Check the pot and amount to call.");
      setAdvice(body);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not get advice.");
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setHeroCards([]); setBoard([]); setActions([]); setAdvice(undefined); setError("");
  }

  function addAction() {
    if (!street || !validFraction || actions.length >= 32) return;
    setActions(previous => [...previous, { ...newAction, street, ...(fraction !== "" ? { pot_fraction: Number(fraction) } : {}) }]);
    setAdvice(undefined);
    setFraction("");
  }

  function changeBoard(next: string[]) {
    setBoard(next);
    setActions(previous => previous.filter(action => STREETS[action.street] <= next.length));
    setAdvice(undefined);
  }

  const heroUsed = new Set(board);
  const boardUsed = new Set(heroCards);

  return (
    <form className="multiway" onSubmit={submit}>
      <p className="muted">
        {useRanges ? `Record public actions to estimate equity against ${opponents} opponent ranges.` :
          `With ${opponents} opponents the Coach estimates your equity against ${opponents} random hands and compares it with the price of a call. Opponent tracking and the solver work heads-up only.`}
      </p>
      <div className="setup-cards">
        <CardInput label="Your cards" slots={["Card 1", "Card 2"]} cards={heroCards} onChange={(next) => { setHeroCards(next); setAdvice(undefined); }} usedCards={heroUsed} keyboard={heroCards.length < 2} />
        <CardInput label="Board" slots={BOARD_SLOTS} cards={board} onChange={changeBoard} usedCards={boardUsed} limit={boardOpen} keyboard={heroCards.length === 2} />
      </div>
      {useRanges && <fieldset>
        <legend>Opponent actions</legend>
        <div className="setup-row">
          <label>Opponent <select value={newAction.seat} onChange={event => setNewAction(value => ({ ...value, seat: Number(event.target.value) }))}>
            {Array.from({ length: opponents }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}
          </select></label>
          <label>Street <select value={street} onChange={event => setNewAction(value => ({ ...value, street: event.target.value as Street }))}>
            {streets.map(name => <option key={name} value={name}>{name}</option>)}
          </select></label>
          <label>Action <select value={newAction.action} onChange={event => setNewAction(value => ({ ...value, action: event.target.value as PublicAction["action"] }))}>
            {Object.entries(PUBLIC_ACTIONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <label>Size in pots<input type="number" min="0" max="100" step="any" value={fraction}
            onChange={event => setFraction(event.target.value)} placeholder="Optional" /></label>
          <button type="button" disabled={!validFraction || actions.length >= 32} className="secondary" onClick={addAction}>Add action</button>
        </div>
        {actions.length > 0 && <ol aria-label="Recorded opponent actions">{actions.map((action, index) =>
          <li key={index}>{action.street} · Opponent {action.seat} · {PUBLIC_ACTIONS[action.action]}
            {action.pot_fraction !== undefined && ` · ${action.pot_fraction} pots`}
            <button type="button" className="secondary" aria-label={`Remove action ${index + 1}`} onClick={() => {
              setActions(previous => previous.filter((_, row) => row !== index)); setAdvice(undefined);
            }}>Remove</button>
          </li>)}</ol>}
      </fieldset>}
      <div className="setup-row">
        <label>Pot now<input inputMode="numeric" value={pot} onChange={(e) => { setPot(e.target.value); setAdvice(undefined); }} /></label>
        <label>To call<input inputMode="numeric" value={toCall} onChange={(e) => { setToCall(e.target.value); setAdvice(undefined); }} /><small>0 if you can check</small></label>
      </div>
      <div className="coach-form-actions">
        <button className="primary" disabled={loading || heroCards.length !== 2}>{loading ? "Working it out…" : <>Get advice <kbd>Enter</kbd></>}</button>
        {(heroCards.length > 0 || advice) && <button type="button" className="secondary" onClick={reset}>New hand</button>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      {advice && (
        <div className="coach-advice" aria-live="polite">
          <h3 className="coach-recommendation">Recommended: {ACTION_TEXT[advice.action]}</h3>
          <p className="coach-reason">{advice.reason}</p>
          <div className="equity-meter" aria-hidden="true">
            <i style={{ width: pct(advice.equity) }} />
            {advice.required_equity > 0 && <b style={{ left: pct(advice.required_equity) }} />}
          </div>
          <dl className="stat-row">
            <div><dt>Your equity</dt><dd>{pct(advice.equity)}</dd></div>
            <div><dt>{advice.required_equity > 0 ? "Needed to call" : "Even share"}</dt><dd>{pct(advice.required_equity > 0 ? advice.required_equity : advice.fair_share)}</dd></div>
            <div><dt>Hand</dt><dd>{[advice.hand_label, ...advice.draws.map((draw) => draw.type)].map((text) => text.replace(/_/g, " ").toLowerCase()).join(" + ")}</dd></div>
          </dl>
          <p className="muted"><small>{advice.note}</small></p>
          {advice.opponent_ranges && <ul aria-label="Estimated opponent ranges">{advice.opponent_ranges.map(range =>
            <li key={range.seat}>Opponent {range.seat} · about {range.effective_combos} effective combinations</li>
          )}</ul>}
        </div>
      )}
    </form>
  );
}
