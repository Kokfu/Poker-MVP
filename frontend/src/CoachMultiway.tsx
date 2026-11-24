import { FormEvent, useState } from "react";
import { CardInput } from "./CardInput";

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
};

const ACTION_TEXT: Record<MultiwayAdvice["action"], string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise" };
const BOARD_SLOTS = ["Flop", "Flop", "Flop", "Turn", "River"];
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

  const boardOpen = heroCards.length === 2 ? (board.length >= 3 ? Math.min(5, board.length + 1) : 3) : 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (heroCards.length !== 2) { setError("Pick your two cards first."); return; }
    if (![0, 3, 4, 5].includes(board.length)) { setError("The board needs 0, 3, 4 or 5 cards. Finish the flop or clear it."); return; }
    setLoading(true);
    try {
      const response = await fetch("/api/coach/multiway", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hero_cards: heroCards, board, opponents, pot: Number(pot) || 0, to_call: Number(toCall) || 0 }),
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
    setHeroCards([]); setBoard([]); setAdvice(undefined); setError("");
  }

  const heroUsed = new Set(board);
  const boardUsed = new Set(heroCards);

  return (
    <form className="multiway" onSubmit={submit}>
      <p className="muted">
        With {opponents} opponents the Coach estimates your equity against {opponents} random hands and compares it with the price of a call.
        Opponent tracking and the solver work heads-up only.
      </p>
      <div className="setup-cards">
        <CardInput label="Your cards" slots={["Card 1", "Card 2"]} cards={heroCards} onChange={(next) => { setHeroCards(next); setAdvice(undefined); }} usedCards={heroUsed} />
        <CardInput label="Board" slots={BOARD_SLOTS} cards={board} onChange={(next) => { setBoard(next); setAdvice(undefined); }} usedCards={boardUsed} limit={boardOpen} />
      </div>
      <div className="setup-row">
        <label>Pot now<input inputMode="numeric" value={pot} onChange={(e) => { setPot(e.target.value); setAdvice(undefined); }} /></label>
        <label>To call<input inputMode="numeric" value={toCall} onChange={(e) => { setToCall(e.target.value); setAdvice(undefined); }} /><small>0 if you can check</small></label>
      </div>
      <div className="coach-form-actions">
        <button className="primary" disabled={loading || heroCards.length !== 2}>{loading ? "Working it out…" : "Get advice"}</button>
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
        </div>
      )}
    </form>
  );
}
