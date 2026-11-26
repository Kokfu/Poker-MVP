import { useEffect, useState } from "react";
import { actionName, CATEGORIES, DrillCards, DrillHistory, drillRequest, type Category, type HistoryEntry } from "./DrillDisplay";
import "./my-leaks.css";

type Source = "coach" | "practice" | "drills";
type Pick = { action: Parameters<typeof actionName>[0]; amount: number | null };
type Metrics = {
  decisions: number;
  different: number;
  costed: number;
  deviation_rate: number | null;
  total_cost_bb: number | null;
  average_cost_bb: number | null;
};
type Group = Metrics & { label: string };
type Example = Pick & {
  best: Pick;
  reference: Pick | null;
  cost_bb: number;
  street: string;
  position: string;
  source: Source;
  spot: { hero_cards: string[]; board: string[]; history: HistoryEntry[]; pot: number; to_call: number };
};
type Coverage = { pending: number; reviewed: number; skipped: number };
type Report = {
  all: Metrics;
  by_source: Group[];
  by_street: Group[];
  by_position: Group[];
  by_category: Group[];
  sessions: (Metrics & { source: Source; start: string; end: string })[];
  top: (Metrics & { category: Category; example: Example })[];
  coverage: Record<Exclude<Source, "drills">, Coverage>;
  drill_attempts: number;
  drill_timeouts: number;
};

const SOURCE = { coach: "Coach", practice: "Practice table", drills: "Drills" } as const;
const POSITION: Record<string, string> = { button: "Button", big_blind: "Big blind" };
const STREET: Record<string, string> = { preflop: "Preflop", flop: "Flop", turn: "Turn", river: "River" };
const OTHER: Record<string, string> = { other_flop: "Other flop", other_river: "Other river" };
const GROUP_LABELS: Record<string, string> = { ...POSITION, ...SOURCE, ...STREET, ...CATEGORIES, ...OTHER };
const DATE = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const bb = (value: number | null) => value === null ? "—" : `${value.toFixed(2)} BB`;
const percent = (value: number | null) => value === null ? "—" : `${Math.round(value * 100)}%`;

export function LeakBreakdown({ title, rows }: { title: string; rows: Group[] }) {
  const ranked = [...rows].sort((a, b) => (b.total_cost_bb ?? -1) - (a.total_cost_bb ?? -1));
  return (
    <div className="leak-breakdown">
      <h3>{title}</h3>
      <table>
        <thead><tr><th scope="col">Group</th><th scope="col">Different</th><th scope="col">Total cost</th><th scope="col">Avg. cost</th></tr></thead>
        <tbody>{ranked.map((row) => <tr key={row.label}>
          <th scope="row">{GROUP_LABELS[row.label] ?? row.label}</th>
          <td title={`${row.different} of ${row.decisions} decisions`}>{percent(row.deviation_rate)} <small>({row.different}/{row.decisions})</small></td>
          <td>{bb(row.total_cost_bb)}</td>
          <td title={`${row.costed} of ${row.decisions} decisions had an EV estimate`}>{bb(row.average_cost_bb)}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}

export default function MyLeaks({ startDrill }: { startDrill: (category: Category) => void }) {
  const [report, setReport] = useState<Report>();
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    let waiting = false;
    const refresh = async () => {
      if (waiting) return;
      waiting = true;
      try {
        const next = await drillRequest<Report>("leaks");
        if (mounted) {
          setReport(next);
          setError("");
        }
      } catch {
        if (mounted) setError("Could not load your leak report. Reconnecting…");
      } finally {
        waiting = false;
      }
    };
    void refresh();
    const id = window.setInterval(refresh, 3500);
    return () => { mounted = false; window.clearInterval(id); };
  }, []);

  if (!report) return <p role="status">{error || "Loading your leak report…"}</p>;

  return (
    <div className="leaks-report">
      {error && <p className="error" role="alert">{error}</p>}
      <div className="leak-summary">
        <div><strong>{report.all.decisions}</strong><span>Decisions reviewed</span></div>
        <div><strong>{percent(report.all.deviation_rate)}</strong><span>Different from solver mix</span></div>
        <div><strong>{bb(report.all.average_cost_bb)}</strong><span>Avg. estimated cost</span></div>
      </div>
      <div className="leak-coverage" aria-label="Review coverage">
        <span>Drills {report.drill_attempts - report.drill_timeouts} reviewed{report.drill_timeouts ? ` · ${report.drill_timeouts} timed out` : ""}</span>
        {(["coach", "practice"] as const).map((source) => {
          const { reviewed, pending, skipped } = report.coverage[source];
          return <span key={source}>{SOURCE[source]} {reviewed} hands reviewed{pending ? ` · ${pending} in queue` : ""}{skipped ? ` · ${skipped} skipped` : ""}</span>;
        })}
      </div>
      <p className="drill-status">Saved hands are replayed with prior opponent history. An exact play in at least 5% of the solver mix, or its best action, counts as a match. Cost averages use decisions with an EV estimate.</p>

      <div className="leak-top">
        <h3>Top leaks</h3>
        {report.top.length === 0 ? <p>Costly differences will appear here as your decisions are reviewed.</p> : report.top.map((leak) => {
          const example = leak.example;
          return <article key={leak.category} className="leak-card">
            <div className="leak-card-heading">
              <div><h4>{CATEGORIES[leak.category]}</h4><p>{bb(leak.total_cost_bb)} across {leak.different} costly {leak.different === 1 ? "difference" : "differences"}</p></div>
              <button type="button" className="secondary" onClick={() => startDrill(leak.category)}>Drill {CATEGORIES[leak.category]}</button>
            </div>
            <div className="drill-table">
              <DrillCards label="Your cards" cards={example.spot.hero_cards} />
              <DrillCards label="Board" cards={example.spot.board} />
              <div className="drill-pot"><span>{SOURCE[example.source]} · {POSITION[example.position]}</span><span>Pot <b>{example.spot.pot}</b></span><span>To call <b>{example.spot.to_call}</b></span></div>
            </div>
            <p>You played <strong>{actionName(example.action, example.amount)}</strong> · Best action <strong>{actionName(example.best.action, example.best.amount)}</strong> · Estimated cost <strong>{bb(example.cost_bb)}</strong></p>
            {example.reference && example.reference.amount !== example.amount && <small>Estimate uses the closest modeled size, {actionName(example.reference.action, example.reference.amount)}.</small>}
            <details><summary>Show action history</summary><DrillHistory history={example.spot.history} /></details>
          </article>;
        })}
      </div>

      {report.all.decisions > 0 && <>
        <div className="leak-breakdown">
          <h3>Recent sessions</h3>
          <table>
            <thead><tr><th scope="col">Session</th><th scope="col">Decisions</th><th scope="col">Different</th><th scope="col">Avg. cost</th></tr></thead>
            <tbody>{report.sessions.map((session) => <tr key={`${session.source}-${session.start}`}>
              <th scope="row">{SOURCE[session.source]} <small>{DATE.format(new Date(session.start))}</small></th>
              <td>{session.decisions}</td><td>{percent(session.deviation_rate)}</td><td>{bb(session.average_cost_bb)}</td>
            </tr>)}</tbody>
          </table>
          <p className="drill-status">Last {report.sessions.length} sessions, oldest first. Coach and drill sessions split after 30 minutes between reviewed actions.</p>
        </div>
        <div className="leak-groups">
          <LeakBreakdown title="By street" rows={report.by_street} />
          <LeakBreakdown title="By position" rows={report.by_position} />
          <LeakBreakdown title="By spot type" rows={report.by_category} />
          <LeakBreakdown title="By source" rows={report.by_source} />
        </div>
      </>}
    </div>
  );
}
