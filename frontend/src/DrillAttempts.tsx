import { useEffect, useState } from "react";
import { CATEGORIES, DrillCards, DrillHistory, actionName, drillRequest, type Category, type Choice, type HistoryEntry } from "./DrillDisplay";
import "./drill-attempts.css";

type ChoiceLabel = { action: Choice; amount: number | null };
type Attempt = {
  id: string;
  created_at: string;
  spot: { category: Category; hero_cards: string[]; board: string[]; history: HistoryEntry[] };
  feedback: ChoiceLabel & {
    correct: boolean;
    elapsed_ms: number;
    cost_bb: number | null;
    best: ChoiceLabel;
    reference: ChoiceLabel | null;
    options: (ChoiceLabel & { frequency: number })[];
  };
};

const DATE = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export function AttemptReview({ attempt }: { attempt: Attempt }) {
  const { spot, feedback } = attempt;
  return (
    <details className="attempt-review">
      <summary>
        <strong>{CATEGORIES[spot.category]}</strong>
        <span>{actionName(feedback.action, feedback.amount)} · {(feedback.elapsed_ms / 1000).toFixed(1)} s</span>
        <span>{feedback.cost_bb == null ? "Cost unavailable" : `${feedback.cost_bb.toFixed(2)} BB`}</span>
        <time className="drill-status" dateTime={attempt.created_at}>{DATE.format(new Date(attempt.created_at))}</time>
      </summary>
      <div className="attempt-review-content">
        <div className="drill-table">
          <DrillCards label="Your cards" cards={spot.hero_cards} />
          <DrillCards label="Board" cards={spot.board} />
        </div>
        <p>Best action <strong>{actionName(feedback.best.action, feedback.best.amount)}</strong>{feedback.correct && " · Score +1"}</p>
        {feedback.reference && feedback.reference.amount !== feedback.amount && <p className="drill-status">Cost estimated using {actionName(feedback.reference.action, feedback.reference.amount)}.</p>}
        <p>Solver mix {feedback.options.map((option) => `${actionName(option.action, option.amount)} ${Math.round(option.frequency * 100)}%`).join(" · ")}</p>
        <DrillHistory history={spot.history} />
      </div>
    </details>
  );
}

export default function DrillAttempts({ filter }: { filter: Category | "" }) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<{ filter: Category | ""; rows?: Attempt[]; error?: boolean }>();

  useEffect(() => {
    if (!open) return;
    let mounted = true;
    const endpoint = filter ? `attempts?category=${encodeURIComponent(filter)}` : "attempts";
    void drillRequest<Attempt[]>(endpoint).then((rows) => {
      if (mounted) setResult({ filter, rows });
    }).catch(() => {
      if (mounted) setResult({ filter, error: true });
    });
    return () => { mounted = false; };
  }, [filter, open]);

  const current = result?.filter === filter ? result : undefined;
  return (
    <details className="drill-attempts" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Recent attempts</summary>
      <div className="drill-attempt-list">
        {!current ? <p role="status">Loading recent attempts…</p>
          : current.error ? <p role="status">Could not load attempts. Close and reopen to retry.</p>
          : current.rows?.length ? current.rows.map((attempt) => <AttemptReview key={attempt.id} attempt={attempt} />)
          : <p>No completed attempts for this filter.</p>}
      </div>
    </details>
  );
}
