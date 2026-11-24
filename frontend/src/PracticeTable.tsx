import { useState } from "react";
import { PlayingCard } from "./CardInput";

type Action = "fold" | "check" | "call" | "bet" | "raise" | "all_in";
type Table = {
  hand: number;
  revision: number;
  status: "your_turn" | "complete";
  position: "BTN" | "BB";
  street: string;
  board: string[];
  your_cards: string[];
  shown_bot_cards?: string[];
  pot: number;
  your_stack: number;
  bot_stack: number;
  to_call: number;
  legal_actions: Action[];
  minimum_target: number | null;
  maximum_target: number;
  actions: { player: "a" | "b"; type: Action; amount?: number }[];
  learned_hands: number;
  net_chips?: number;
};

const LABEL: Record<Action, string> = {
  fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise to", all_in: "All-in",
};

export default function PracticeTable() {
  const [key, setKey] = useState("");
  const [table, setTable] = useState<Table>();
  const [pending, setPending] = useState(false);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  async function request(path = "", payload?: object) {
    setPending(true);
    setError("");
    const headers = new Headers({ "Content-Type": "application/json" });
    if (key) headers.set("Authorization", `Bearer ${key}`);
    try {
      const response = await fetch(`/api/practice/table${path}`, {
        method: "POST",
        headers,
        body: payload ? JSON.stringify(payload) : undefined,
      });
      if (!response.ok) {
        if (key && response.status === 409) {
          const fresh = await fetch("/api/practice/table", { headers: { Authorization: `Bearer ${key}` } });
          if (fresh.ok) update(await fresh.json());
        }
        const problem = await response.json();
        throw new Error(typeof problem.detail === "string" ? problem.detail : "Practice table request failed");
      }
      const body = await response.json();
      if (!key) setKey(body.key);
      update(key ? body : body.table);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Practice table request failed");
    } finally {
      setPending(false);
    }
  }

  function update(state: Table) {
    setTable(state);
    setAmount(state.minimum_target === null ? "" : String(state.minimum_target));
  }

  return (
    <section className="panel" aria-labelledby="practice-title">
      <h2 id="practice-title">Heads-up practice</h2>
      <p className="muted">Play chips · 50/100 blinds · stacks reset each hand.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {!table ? (
        <button className="primary" disabled={pending} onClick={() => request()}>Start practice table</button>
      ) : (
        <>
          <p>Hand {table.hand} · {table.position === "BTN" ? "Button / SB" : "Big blind"} · {table.status === "complete" ? "Complete" : table.street}</p>
          <div className="coach-action-row">
            <p><strong>You</strong> · {table.your_stack} chips</p>
            <p><strong>Solver bot</strong> · {table.bot_stack} chips</p>
          </div>
          <div className="coach-action-row" aria-label="Your cards">{table.your_cards.map(card => <PlayingCard key={card} card={card} />)}</div>
          <p>Pot {table.pot}{table.to_call > 0 && ` · ${table.to_call} to call`}</p>
          {table.board.length > 0 && <div className="coach-action-row" aria-label="Board">{table.board.map(card => <PlayingCard key={card} card={card} />)}</div>}
          {table.shown_bot_cards && <div className="coach-action-row" aria-label="Solver bot showdown cards">{table.shown_bot_cards.map(card => <PlayingCard key={card} card={card} />)}</div>}
          {table.actions.length > 0 && <ul aria-label="Recent actions">{table.actions.slice(-6).map((action, index) => (
            <li key={index}>{action.player === "a" ? "You" : "Solver bot"} · {action.type === "raise" ? "Raise" : LABEL[action.type]}{action.amount ? ` · ${action.amount} chips added` : ""}</li>
          ))}</ul>}
          {table.status === "complete" ? (
            <>
              <p role="status">Hand complete · {(table.net_chips ?? 0) > 0 && "+"}{table.net_chips} chips · {table.learned_hands} {table.learned_hands === 1 ? "hand" : "hands"} observed by the bot</p>
              <button className="primary" disabled={pending} onClick={() => request("/next", { revision: table.revision })}>Next practice hand</button>
            </>
          ) : (
            <>
              <h3>Your turn</h3>
              {(table.legal_actions.includes("bet") || table.legal_actions.includes("raise")) && (
                <label>Street total <input type="number" inputMode="numeric" min={table.minimum_target ?? 0} max={table.maximum_target} value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
              )}
              <div className="coach-action-row">
                {table.legal_actions.map(action => {
                  const sized = action === "bet" || action === "raise";
                  return <button key={action} className="secondary" disabled={pending || (sized && (!Number.isInteger(+amount) || +amount < (table.minimum_target ?? 1) || +amount > table.maximum_target))}
                    onClick={() => request("/action", { revision: table.revision, action, ...(sized ? { amount: +amount } : {}) })}>
                    {LABEL[action]}{action === "call" && ` ${table.to_call}`}
                  </button>;
                })}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
