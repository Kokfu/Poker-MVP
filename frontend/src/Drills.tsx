import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { isTypingTarget } from "./CardInput";
import { ACTION_NAMES, actionName, CATEGORIES, DrillCards, DrillHistory, drillRequest, type Action, type Category, type Choice, type HistoryEntry } from "./DrillDisplay";
import MyLeaks from "./MyLeaks";
import "./drills.css";

type Spot = {
  id: string;
  category: Category;
  street: string;
  position: "button" | "big_blind";
  hero_cards: string[];
  board: string[];
  history: HistoryEntry[];
  pot: number;
  to_call: number;
  hero_stack: number;
  opponent_stack: number;
  legal_actions: Action[];
  minimum_target: number | null;
  maximum_target: number;
  remaining_ms: number;
};
type Option = { action: Action; amount: number | null; frequency: number; ev: number | null };
type Feedback = {
  action: Choice;
  amount: number | null;
  elapsed_ms: number;
  options: Option[];
  best: Option;
  reference: Option | null;
  correct: boolean;
  cost_bb: number | null;
};
type Stats = {
  ready: Partial<Record<Category, number>>;
  categories: {
    category: Category; attempts: number; correct: number; average_ms: number;
    average_cost_bb: number | null; costed: number;
  }[];
};

const SECONDS_KEY = "drills.seconds";
const TURN_KEY = "drills.turn";
const ACTION_KEYS = { fold: "F", check: "C", call: "C", bet: "B", raise: "B", all_in: "A" };

function savedSeconds() {
  const seconds = Number(localStorage.getItem(SECONDS_KEY));
  return Number.isInteger(seconds) && seconds >= 3 && seconds <= 120 ? seconds : 15;
}

function savedTurn(): { id: string; filter: Category | "" } | null {
  const saved = sessionStorage.getItem(TURN_KEY);
  if (!saved) return null;
  try {
    const { id, filter } = JSON.parse(saved);
    return typeof id === "string" && (filter === "" || Object.hasOwn(CATEGORIES, filter)) ? { id, filter } : null;
  } catch {
    return null;
  }
}

export default function Drills() {
  const [view, setView] = useState<"drills" | "leaks">("drills");
  const [restoring, setRestoring] = useState(() => Boolean(savedTurn()));
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [category, setCategory] = useState<Category | "">("");
  const [seconds, setSeconds] = useState(() => String(savedSeconds()));
  const [spot, setSpot] = useState<Spot | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [amount, setAmount] = useState("");
  const [remaining, setRemaining] = useState(0);
  const [stats, setStats] = useState<Stats>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const deadline = useRef(0);
  const request = useRef(false);
  const expired = useRef(false);
  const amountValue = useRef("");
  const active = Boolean(spot && !feedback);
  const sizedAction = spot?.legal_actions.find((action) => action === "bet" || action === "raise");
  const selectedReady = category ? stats?.ready[category] ?? 0 : Object.values(stats?.ready ?? {}).reduce((sum, n) => sum + n, 0);

  const refreshStats = useCallback(async () => {
    setStats(await drillRequest<Stats>("stats"));
  }, []);

  useEffect(() => {
    const saved = savedTurn();
    if (!saved) return;
    let mounted = true;
    void drillRequest<{ spot: Spot; feedback: Feedback | null } | null>(`turns/${encodeURIComponent(saved.id)}`).then((round) => {
      if (!mounted) return;
      if (round) {
        deadline.current = performance.now() + round.spot.remaining_ms;
        setCategory(saved.filter);
        setRemaining(round.spot.remaining_ms);
        setSpot(round.spot);
        setFeedback(round.feedback);
      } else {
        sessionStorage.removeItem(TURN_KEY);
      }
      setRestoring(false);
    }).catch(() => {
      if (mounted) setError("Could not restore this drill. Reconnect and try again.");
    });
    return () => { mounted = false; };
  }, [restoreAttempt]);

  useEffect(() => {
    if (active || restoring || view === "leaks") return;
    let mounted = true;
    const refresh = () => refreshStats().catch(() => {
      if (mounted) setStats(undefined);
    });
    void refresh();
    const id = window.setInterval(refresh, 3500);
    return () => { mounted = false; window.clearInterval(id); };
  }, [active, refreshStats, restoring, view]);

  function updateAmount(value: string) {
    amountValue.current = value.replace(/[^0-9]/g, "").slice(0, 10);
    setAmount(amountValue.current);
  }

  async function start(filter = category) {
    if (request.current) return;
    const limit = Number(seconds);
    if (!Number.isInteger(limit) || limit < 3 || limit > 120) {
      setError("Set a time limit of 3–120 seconds.");
      return;
    }
    request.current = true;
    setBusy(true);
    setError("");
    try {
      const next = await drillRequest<Spot | null>("start", { category: filter || null, seconds: limit });
      if (!next) {
        setError("This category is being prepared. Try again when a spot is ready.");
        await refreshStats();
        return;
      }
      localStorage.setItem(SECONDS_KEY, String(limit));
      sessionStorage.setItem(TURN_KEY, JSON.stringify({ id: next.id, filter }));
      deadline.current = performance.now() + next.remaining_ms;
      expired.current = false;
      setRemaining(next.remaining_ms);
      updateAmount("");
      setFeedback(null);
      setSpot(next);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not start a drill.");
    } finally {
      request.current = false;
      setBusy(false);
    }
  }

  const submit = useCallback(async (action: Choice) => {
    if (!spot || feedback || request.current) return;
    let target = null;
    if (action === "bet" || action === "raise") {
      // The default is a public sizing rule and reveals no stored advice.
      const minimum = spot.minimum_target ?? 0;
      const defaultTarget = spot.street === "preflop" && spot.history.length === 0 ? 250
        : minimum + Math.max(0, Math.round(spot.pot / 2) - spot.to_call);
      target = amountValue.current ? Number(amountValue.current) : Math.min(spot.maximum_target, Math.max(minimum, defaultTarget));
      if (target < minimum || target > spot.maximum_target) {
        setError(`Enter a total between ${minimum} and ${spot.maximum_target}.`);
        return;
      }
    }
    request.current = true;
    setBusy(true);
    setError("");
    try {
      setFeedback(await drillRequest<Feedback>(`${spot.id}/answer`, { action, amount: target }));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save this answer.");
    } finally {
      request.current = false;
      setBusy(false);
    }
  }, [spot, feedback]);

  useEffect(() => {
    if (!active) return;
    const tick = () => {
      const left = Math.max(0, deadline.current - performance.now());
      setRemaining(left);
      if (left === 0 && !expired.current && !request.current) {
        expired.current = true;
        void submit("timeout");
      }
    };
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
  }, [active, spot, submit]);

  useLayoutEffect(() => {
    if (!active || !spot || busy || remaining === 0) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      const key = event.key.toUpperCase();
      if (sizedAction && /^[0-9]$/.test(key)) {
        event.preventDefault();
        updateAmount(amountValue.current + key);
      } else if (sizedAction && key === "BACKSPACE" && amountValue.current) {
        event.preventDefault();
        updateAmount(amountValue.current.slice(0, -1));
      } else {
        const action = key === "ENTER" && amountValue.current ? sizedAction
          : spot.legal_actions.find((candidate) => ACTION_KEYS[candidate] === key);
        if (action) {
          event.preventDefault();
          void submit(action);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, spot, busy, remaining, sizedAction, submit]);

  return (
    <section className="drills-panel" aria-labelledby="drills-heading">
      <h2 id="drills-heading">{view === "leaks" ? "My leaks" : "Timed drills"}</h2>
      <nav className="drill-views" aria-label="Study views">
        <button type="button" aria-pressed={view === "drills"} onClick={() => setView("drills")}>Trainer</button>
        <button type="button" aria-pressed={view === "leaks"} disabled={active || busy || restoring} onClick={() => setView("leaks")}>My leaks</button>
      </nav>
      {restoring ? <div className="drill-restore">
        <p role="status">{error || "Restoring your drill…"}</p>
        {error && <button type="button" onClick={() => { setError(""); setRestoreAttempt((attempt) => attempt + 1); }}>Retry restore</button>}
      </div> : view === "leaks" ? <MyLeaks startDrill={(filter) => {
        setView("drills");
        setCategory(filter);
        void start(filter);
      }} /> : <>
      <div className="drill-toolbar">
        <label>Spot category<select value={category} disabled={active || busy} onChange={(event) => setCategory(event.target.value as Category | "")}>
          <option value="">All categories</option>
          {Object.entries(CATEGORIES).map(([id, label]) => <option value={id} key={id}>{label}</option>)}
        </select></label>
        <label>Seconds per spot<input type="number" min="3" max="120" value={seconds} disabled={active || busy} onChange={(event) => setSeconds(event.target.value)} /></label>
        <button type="button" className="primary" disabled={active || busy || !selectedReady} onClick={() => void start()}>
          {spot ? "Next drill" : "Start drill"}
        </button>
      </div>
      {!active && <p className="drill-status" role="status">{!stats ? "Connecting to the drill service…" : selectedReady ? `${selectedReady} ${selectedReady === 1 ? "spot" : "spots"} ready` : "Preparing spots in the background…"}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {spot && (
        <div className="drill-spot">
          <div className="drill-spot-heading">
            <h3>{CATEGORIES[spot.category]} · {spot.position === "button" ? "Button" : "Big blind"}</h3>
            {active && <strong className={remaining < 5000 ? "drill-clock drill-clock-low" : "drill-clock"} role="timer" aria-label="Time remaining">{Math.ceil(remaining / 1000)} s</strong>}
          </div>
          <div className="drill-table">
            <DrillCards label="Your cards" cards={spot.hero_cards} />
            <DrillCards label="Board" cards={spot.board} />
            <div className="drill-pot"><span>Pot <b>{spot.pot}</b></span><span>To call <b>{spot.to_call}</b></span><span>Your stack <b>{spot.hero_stack}</b></span><span>Opponent stack <b>{spot.opponent_stack}</b></span></div>
          </div>
          <DrillHistory history={spot.history} />
          {active && remaining > 0 && (
            <div className="drill-controls">
              <div className="drill-buttons" role="group" aria-label="Your action">
                {spot.legal_actions.map((action) => (
                  <button type="button" key={action} disabled={busy} onClick={() => void submit(action)}>
                    {ACTION_NAMES[action]}{action === "call" ? ` ${spot.to_call}` : ""} <kbd aria-hidden="true">{ACTION_KEYS[action]}</kbd>
                  </button>
                ))}
              </div>
              {sizedAction && <label className="drill-size">Total this street <small>({spot.minimum_target}–{spot.maximum_target})</small>
                <input inputMode="numeric" value={amount} disabled={busy} onChange={(event) => updateAmount(event.target.value)} onKeyDown={(event) => {
                  if (event.key === "Enter" && amountValue.current) {
                    event.preventDefault();
                    void submit(sizedAction);
                  }
                }} />
              </label>}
            </div>
          )}
          {active && remaining === 0 && !busy && <button type="button" onClick={() => void submit("timeout")}>Show answer</button>}
          {feedback && <div className="drill-feedback" aria-live="polite">
            <h3>Best action · {actionName(feedback.best.action, feedback.best.amount)}</h3>
            <p>{feedback.action === "timeout" ? "Time expired" : `You chose ${actionName(feedback.action, feedback.amount)}`} · {(feedback.elapsed_ms / 1000).toFixed(1)} s{feedback.correct ? " · Score +1" : ""}</p>
            <p>Estimated cost <strong>{feedback.cost_bb === null ? "Unavailable" : `${feedback.cost_bb.toFixed(2)} BB`}</strong>
              {feedback.reference && feedback.reference.amount !== feedback.amount && ` using the closest modeled size (${actionName(feedback.reference.action, feedback.reference.amount)})`}.</p>
            <h4>Solver mix</h4>
            <ul>{feedback.options.map((option) => <li key={actionName(option.action, option.amount)}>{actionName(option.action, option.amount)} <b>{Math.round(option.frequency * 100)}%</b></li>)}</ul>
          </div>}
        </div>
      )}

      <div className="drill-stats">
        <h3>Category scores</h3>
        <p className="drill-status">Score one point for the best action or an exact action in at least 5% of the solver mix.</p>
        {stats?.categories.length ? <table>
          <thead><tr><th scope="col">Category</th><th scope="col">Score</th><th scope="col">Avg. time</th><th scope="col">Avg. cost</th></tr></thead>
          <tbody>{stats.categories.map((row) => <tr key={row.category}>
            <th scope="row">{CATEGORIES[row.category]}</th><td>{row.correct}/{row.attempts}</td>
            <td>{(row.average_ms / 1000).toFixed(1)} s</td><td title={`${row.costed} of ${row.attempts} attempts had an EV estimate`}>{row.average_cost_bb === null ? "—" : `${row.average_cost_bb.toFixed(2)} BB`}</td>
          </tr>)}</tbody>
        </table> : <p>Finish a drill to see your score.</p>}
      </div>
      </>}
    </section>
  );
}
