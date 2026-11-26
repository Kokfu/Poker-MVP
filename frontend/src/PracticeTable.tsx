import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { isTypingTarget, PlayingCard } from "./CardInput";

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
  turn_seconds: number;
  remaining_ms: number | null;
  last_action_timed_out?: boolean;
  opponent: string;
  completed_hands: number;
};

type Play = { action: Action; amount: number | null };
type Review = { street: string; action: Play; advice: Play; timed_out: boolean; explain: { reason: string } | null; estimated_cost: number | null; mistake?: boolean };
type SessionReview = { completed_hands: number; hands: { hand: number; decisions: Review[]; estimated_cost: number | null }[] };
type Seat = { key: string; opponent: string };
type SavedSeats = { seats: Seat[]; active: string };
const TABLE_STORAGE = "poker.practice.seats";
const MAX_LOCAL_TABLES = 2;

const LABEL: Record<Action, string> = {
  fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise to", all_in: "All-in",
};

const ACTION_KEY: Record<Action, string> = {
  fold: "F", check: "C", call: "C", bet: "B", raise: "B", all_in: "A",
};

function isSizedAction(action: Action): boolean {
  return action === "bet" || action === "raise";
}

type PracticeShortcut = { action: Action | "next" } | { digit: string };

export function practiceShortcut(key: string, onButton: boolean, complete: boolean,
  legal: readonly Action[], hasTypedTotal: boolean): PracticeShortcut | undefined {
  if (complete) return key.toUpperCase() === "N" ? { action: "next" } : undefined;
  const sizedAction = legal.find(isSizedAction);
  if (/^[0-9]$/.test(key)) return sizedAction ? { digit: key } : undefined;
  if (key === "Enter") return !onButton && hasTypedTotal && sizedAction ? { action: sizedAction } : undefined;
  const action = legal.find(candidate => ACTION_KEY[candidate] === key.toUpperCase());
  return action ? { action } : undefined;
}

function playLabel(play: Play) {
  return play.amount === null ? LABEL[play.action] : `${LABEL[play.action]} ${play.amount}`;
}

function savedSeats(): SavedSeats {
  try {
    const value = JSON.parse(sessionStorage.getItem(TABLE_STORAGE) ?? "null");
    if (Array.isArray(value?.seats)) {
      const seats: Seat[] = value.seats.filter((seat: Partial<Seat> | null) =>
        typeof seat?.key === "string" && /^[A-Za-z0-9_-]{43}$/.test(seat.key)
        && typeof seat.opponent === "string").slice(0, MAX_LOCAL_TABLES);
      const active = seats.some(seat => seat.key === value.active) ? value.active : "";
      return { seats, active };
    }
  } catch {
    // The server session can still be used if browser storage is unavailable.
  }
  return { seats: [], active: "" };
}

export default function PracticeTable() {
  const [{ seats, active }, setSaved] = useState(savedSeats);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    try {
      sessionStorage.setItem(TABLE_STORAGE, JSON.stringify({ seats, active }));
    } catch {
      // Storage is optional. Open tables still operate in this page.
    }
  }, [seats, active]);

  // A table that finishes opening after the player switched away is kept, but doesn't take focus.
  const opened = useCallback((seat: Seat, activate: boolean) => {
    setSaved(previous => ({ seats: [...previous.seats, seat], active: activate ? seat.key : previous.active }));
  }, []);
  const closed = useCallback((key: string, message?: string) => {
    setNotice(message ?? "");
    setSaved(previous => {
      const remainingSeats = previous.seats.filter(seat => seat.key !== key);
      return { seats: remainingSeats, active: previous.active === key ? remainingSeats[0]?.key ?? "" : previous.active };
    });
  }, []);
  const select = (key: string) => {
    setNotice("");
    setSaved(previous => ({ ...previous, active: key }));
  };
  return (
    <section className="panel" aria-labelledby="practice-title">
      <h2 id="practice-title">Heads-up practice</h2>
      <p className="muted">Play chips · 50/100 blinds · stacks reset each hand.</p>
      {notice && <p role="status">{notice}</p>}
      {seats.length > 0 && <nav className="coach-action-row" aria-label="Practice tables">
        {seats.map((seat, index) => <button className="secondary" key={seat.key}
          aria-current={active === seat.key ? "true" : undefined} onClick={() => select(seat.key)}>
          Table {index + 1} · {seat.opponent}
        </button>)}
        {active && seats.length < MAX_LOCAL_TABLES && <button className="secondary" onClick={() => select("")}>New table</button>}
      </nav>}
      <PracticeSeat key={active || "new"} seatKey={active} onOpen={opened} onClose={closed} />
    </section>
  );
}

function PracticeSeat({ seatKey: key, onOpen, onClose }: {
  seatKey: string;
  onOpen: (seat: Seat, activate: boolean) => void;
  onClose: (key: string, message?: string) => void;
}) {
  const [table, setTable] = useState<Table>();
  const [pending, setPending] = useState(false);
  const [amount, setAmount] = useState("");
  const [typed, setTyped] = useState(false);
  const [error, setError] = useState("");
  const [turnSeconds, setTurnSeconds] = useState("20");
  const [opponent, setOpponent] = useState("Solver bot");
  const [deadline, setDeadline] = useState<number>();
  const [remaining, setRemaining] = useState(0);
  const [review, setReview] = useState<Review[]>();
  const [reviewError, setReviewError] = useState("");
  const [showSession, setShowSession] = useState(false);
  const [session, setSession] = useState<SessionReview>();
  const [sessionError, setSessionError] = useState("");
  const pendingRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const update = useCallback((state: Table) => {
    setTable(state);
    setAmount(state.minimum_target === null ? "" : String(state.minimum_target));
    setTyped(false);
    setRemaining(Math.ceil((state.remaining_ms ?? 0) / 1000));
    setDeadline(state.remaining_ms === null ? undefined : performance.now() + state.remaining_ms);
  }, []);

  const request = useCallback(async (path = "", payload?: object, method = "POST") => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    const headers = new Headers({ "Content-Type": "application/json" });
    if (key) headers.set("Authorization", `Bearer ${key}`);
    try {
      const response = await fetch(`/api/practice/table${path}`, {
        method,
        headers,
        body: payload ? JSON.stringify(payload) : undefined,
      });
      if (!response.ok) {
        if (key && response.status === 404) {
          onClose(key, "That table is no longer available.");
          return;
        }
        if (key && response.status === 409) {
          const fresh = await fetch("/api/practice/table", { headers: { Authorization: `Bearer ${key}` } });
          if (fresh.ok) update(await fresh.json());
        }
        const problem = await response.json();
        throw new Error(typeof problem.detail === "string" ? problem.detail : "Practice table request failed");
      }
      if (method === "DELETE") {
        onClose(key);
        return;
      }
      const body = await response.json();
      if (!key) {
        onOpen({ key: body.key, opponent: body.table.opponent }, mounted.current);
      } else {
        update(body);
      }
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Practice table request failed");
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }, [key, onClose, onOpen, update]);

  useEffect(() => {
    if (key) void request("", undefined, "GET");
  }, [key, request]);

  useEffect(() => {
    if (deadline === undefined) return;
    const interval = window.setInterval(() => {
      const seconds = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
      setRemaining(seconds);
      if (seconds === 0 && !pendingRef.current) {
        window.clearInterval(interval);
        void request("", undefined, "GET");
      }
    }, 100);
    return () => window.clearInterval(interval);
  }, [deadline, request]);

  const completedRevision = table?.status === "complete" ? table.revision : undefined;
  useEffect(() => {
    setReview(undefined);
    setReviewError("");
    if (!key || completedRevision === undefined) return;
    const abort = new AbortController();
    fetch(`/api/practice/table/review?revision=${completedRevision}`, {
      headers: { Authorization: `Bearer ${key}` }, signal: abort.signal,
    }).then(response => {
      if (!response.ok) throw new Error("Coach review could not be loaded.");
      return response.json();
    }).then(rows => {
      if (!abort.signal.aborted) setReview(rows);
    }).catch(() => {
      if (!abort.signal.aborted) setReviewError("Coach review could not be loaded.");
    });
    return () => abort.abort();
  }, [completedRevision, key]);

  const completedHands = table?.completed_hands;
  useEffect(() => {
    setSession(undefined);
    setSessionError("");
    if (!showSession || !key) return;
    const abort = new AbortController();
    fetch("/api/practice/table/session", {
      headers: { Authorization: `Bearer ${key}` }, signal: abort.signal,
    }).then(response => {
      if (!response.ok) throw new Error("Session review could not be loaded.");
      return response.json();
    }).then(summary => {
      if (!abort.signal.aborted) setSession(summary);
    }).catch(() => {
      if (!abort.signal.aborted) setSessionError("Session review could not be loaded.");
    });
    return () => abort.abort();
  }, [completedHands, key, showSession]);

  const validTotal = table !== undefined && Number.isInteger(+amount)
    && +amount >= (table.minimum_target ?? 1) && +amount <= table.maximum_target;
  const nextHand = () => {
    if (table?.status === "complete") void request("/next", { revision: table.revision });
  };
  const play = (action: Action) => {
    if (table?.status !== "your_turn" || remaining === 0 || (isSizedAction(action) && !validTotal)) return;
    void request("/action", { revision: table.revision, action, ...(isSizedAction(action) ? { amount: +amount } : {}) });
  };
  useLayoutEffect(() => {
    if (!table) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey ||
        event.isComposing || isTypingTarget(event.target) || pendingRef.current) return;
      if (table.status === "your_turn" && remaining === 0) return;
      const onButton = (event.target as HTMLElement | null)?.tagName === "BUTTON";
      const shortcut = practiceShortcut(event.key, onButton, table.status === "complete", table.legal_actions, typed);
      if (!shortcut) return;
      event.preventDefault();
      if ("digit" in shortcut) {
        setAmount(typed ? amount + shortcut.digit : shortcut.digit);
        setTyped(true);
      } else if (shortcut.action === "next") {
        if (!event.repeat) nextHand();
      } else if (!event.repeat) {
        play(shortcut.action);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const validTimer = Number.isInteger(+turnSeconds) && +turnSeconds >= 1 && +turnSeconds <= 120;

  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      {!key ? (
        <div className="coach-action-row">
          <label>Seconds per action <input type="number" inputMode="numeric" min="1" max="120" value={turnSeconds}
            onChange={event => setTurnSeconds(event.target.value)} /></label>
          <label>Opponent name <input maxLength={60} value={opponent} onChange={event => setOpponent(event.target.value)} /></label>
          <button className="primary" disabled={pending || !validTimer || !opponent.trim()}
            onClick={() => request("", { turn_seconds: +turnSeconds, opponent })}>Start practice table</button>
        </div>
      ) : !table ? (
        error ? <button onClick={() => request("", undefined, "GET")} disabled={pending}>Reconnect</button> :
          <p role="status">Connecting to practice table…</p>
      ) : (
        <>
          <p>Hand {table.hand} · {table.position === "BTN" ? "Button / SB" : "Big blind"} · {table.status === "complete" ? "Complete" : table.street}</p>
          <div className="coach-action-row">
            <p><strong>You</strong> · {table.your_stack} chips</p>
            <p><strong>{table.opponent}</strong> <span>BOT</span> · {table.bot_stack} chips</p>
          </div>
          <div className="coach-action-row" aria-label="Your cards">{table.your_cards.map(card => <PlayingCard key={card} card={card} />)}</div>
          <p>Pot {table.pot}{table.to_call > 0 && ` · ${table.to_call} to call`}</p>
          {table.last_action_timed_out && <p role="status">Timer expired. The table played your previous action.</p>}
          {table.board.length > 0 && <div className="coach-action-row" aria-label="Board">{table.board.map(card => <PlayingCard key={card} card={card} />)}</div>}
          {table.shown_bot_cards && <div className="coach-action-row" aria-label="Solver bot showdown cards">{table.shown_bot_cards.map(card => <PlayingCard key={card} card={card} />)}</div>}
          {table.actions.length > 0 && <ul aria-label="Recent actions">{table.actions.slice(-6).map((action, index) => (
            <li key={index}>{action.player === "a" ? "You" : table.opponent} · {action.type === "raise" ? "Raise" : LABEL[action.type]}{action.amount ? ` · ${action.amount} chips added` : ""}</li>
          ))}</ul>}
          {table.status === "complete" ? (
            <>
              <p role="status">Hand complete · {(table.net_chips ?? 0) > 0 && "+"}{table.net_chips} chips · {table.learned_hands} {table.learned_hands === 1 ? "hand" : "hands"} observed by the bot</p>
              <h3>Coach review</h3>
              {reviewError ? <p role="alert">{reviewError}</p> : !review ? <p role="status">Loading advice…</p> :
                <ol>{review.map((decision, index) => <li key={index}>
                  <strong>{decision.street}</strong> · You played {playLabel(decision.action)}{decision.timed_out && " (timer)"} · Coach suggests {playLabel(decision.advice)}{decision.mistake === false && " · your play is also fine (the Coach mixes)"}
                  {decision.explain && <p>{decision.explain.reason}</p>}
                </li>)}</ol>}
              <button className="primary" disabled={pending} aria-keyshortcuts="N" onClick={nextHand}>
                Next practice hand <kbd aria-hidden="true">N</kbd>
              </button>
            </>
          ) : (
            <>
              <h3>Your turn</h3>
              <p role="timer" aria-label="Time left">{remaining} s left</p>
              {remaining === 0 && error && <button disabled={pending} onClick={() => request("", undefined, "GET")}>Refresh turn</button>}
              {table.legal_actions.some(isSizedAction) && (
                <>
                  <label>Street total <input type="number" inputMode="numeric" min={table.minimum_target ?? 0} max={table.maximum_target} value={amount} onChange={(event) => { setAmount(event.target.value); setTyped(true); }} /></label>
                  <p className="kbd-help">Click outside the controls, type a total, then press <kbd>Enter</kbd>.</p>
                </>
              )}
              <div className="coach-action-row">
                {table.legal_actions.map(action => (
                  <button key={action} className="secondary" disabled={pending || remaining === 0 || (isSizedAction(action) && !validTotal)}
                    aria-keyshortcuts={ACTION_KEY[action]} onClick={() => play(action)}>
                    {LABEL[action]}{action === "call" && ` ${table.to_call}`}
                    <span className="key-hint" aria-hidden="true">{ACTION_KEY[action]}</span>
                  </button>
                ))}
              </div>
            </>
          )}
          {table.completed_hands > 0 && <button className="secondary" type="button" aria-expanded={showSession}
            onClick={() => setShowSession(value => !value)}>{showSession ? "Hide session review" : "Review last session"}</button>}
          {showSession && <section aria-label="Session review">
            <h3>Session review</h3>
            {sessionError ? <p role="alert">{sessionError}</p> : !session ? <p role="status">Loading session review…</p> :
              session.hands.length === 0 ? <p>No mistakes: every play in the completed hands is one the Coach also makes.</p> :
              <>
                <p className="muted">Estimated cost compares the two plays in the Coach model. Custom sizes may have no estimate.</p>
                <ul>{session.hands.map(hand => <li key={hand.hand}>
                  <strong>Hand {hand.hand}</strong> · {hand.estimated_cost === null ? "Total cost unavailable" : `Estimated cost ${hand.estimated_cost} chips`}
                  <ul>{hand.decisions.map((decision, index) => <li key={index}>
                    {decision.street} · {playLabel(decision.action)} instead of {playLabel(decision.advice)} ·
                    {decision.estimated_cost === null ? " cost unavailable" : ` ${decision.estimated_cost} chips`}
                  </li>)}</ul>
                </li>)}</ul>
              </>}
          </section>}
          <button className="secondary" disabled={pending} onClick={() => request("", undefined, "DELETE")}>Close table</button>
        </>
      )}
    </>
  );
}
