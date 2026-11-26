import { PlayingCard } from "./CardInput";

export const CATEGORIES = {
  preflop_open: "Preflop open",
  preflop_defend: "Preflop defend",
  preflop_three_bet: "Facing a 3-bet",
  flop_cbet: "Flop c-bet",
  flop_defend: "Flop defend",
  turn: "Turn",
  river_call: "River call",
  river_bluff: "River bluff",
} as const;

export type Category = keyof typeof CATEGORIES;
export type Action = "fold" | "check" | "call" | "bet" | "raise" | "all_in";
export type Choice = Action | "timeout";
export type HistoryEntry = { street: string; actor: string; action: Action; amount: number | null };

export const ACTION_NAMES = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise", all_in: "All-in", timeout: "Time expired" };

export function actionName(action: Choice, amount?: number | null) {
  return `${ACTION_NAMES[action]}${amount == null ? "" : ` to ${amount.toLocaleString()}`}`;
}

export async function drillRequest<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/drills/${path}`, body === undefined ? { cache: "no-store" } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "The drill request failed.");
  return value;
}

export function DrillCards({ label, cards }: { label: string; cards: string[] }) {
  return (
    <div className="drill-cards">
      <h3>{label}</h3>
      <div>{cards.length === 0 ? <small>Preflop</small> : cards.map((card) => <PlayingCard card={card} key={card} />)}</div>
    </div>
  );
}

export function DrillHistory({ history }: { history: HistoryEntry[] }) {
  return (
    <div className="drill-history">
      <h3>Action so far</h3>
      {history.length === 0 ? <p>Blinds posted.</p> : (
        <ol>{history.map((entry, index) => (
          <li key={index}><span>{entry.street}</span> {entry.actor === "hero" ? "You" : "Opponent"} · {actionName(entry.action, entry.amount)}</li>
        ))}</ol>
      )}
    </div>
  );
}
