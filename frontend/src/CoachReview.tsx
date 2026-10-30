import { useEffect, useState } from "react";

type Stat = { frequency: number | null; opportunities: number; occurrences: number; confidence: string };
type Review = {
  opponent: string | null;
  results: { hands: number; hands_with_known_result: number; net_bb: number; bb_per_100: number | null; showdowns: number; showdowns_with_known_result: number; skipped_hands: number; note: string };
  stats: Record<string, Stat>;
  leaks: { stat: string; issue: string; advice: string; frequency: number; opportunities: number; confidence: string }[];
  by_opponent: { opponent: string; hands: number; known_hands: number; net_bb: number }[];
};

const STAT_NAMES: Record<string, string> = {
  vpip: "Plays hand (VPIP)", pfr: "Raises preflop (PFR)", three_bet: "3-bets", fold_to_preflop_raise: "Folds to preflop raise",
  postflop_bet: "Bets when checked to", fold_to_bet: "Folds to postflop bet", showdown_win: "Wins at showdown",
};
const percent = (value: number | null) => (value === null ? "-" : `${Math.round(value * 100)}%`);

export default function CoachReview({ opponents }: { opponents: { name: string; hands: number }[] }) {
  const [opponent, setOpponent] = useState("");
  const [review, setReview] = useState<Review>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    const query = opponent ? `?opponent=${encodeURIComponent(opponent)}` : "";
    fetch(`/api/coach/review${query}`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Could not load the review.");
        return response.json();
      })
      .then((body) => { if (current) setReview(body); })
      .catch((problem: Error) => { if (current) setError(problem.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [opponent]);

  return (
    <div className="coach-review">
      <label>Opponent
        <select value={opponent} onChange={(event) => setOpponent(event.target.value)}>
          <option value="">All opponents</option>
          {opponents.map((item) => <option key={item.name} value={item.name}>{item.name} ({item.hands})</option>)}
        </select>
      </label>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {review && review.results.hands === 0 && !loading && <p className="muted">No logged hands yet. Finish a hand in "Play a hand" and log it under an opponent's name.</p>}
      {review && review.results.hands > 0 && (
        <>
          <ul className="coach-review-stats">
            <li><small>HANDS</small><b>{review.results.hands}</b><small>{review.results.hands_with_known_result} with a known result</small></li>
            <li><small>NET RESULT</small><b className={review.results.net_bb >= 0 ? "positive" : "negative"}>{review.results.net_bb >= 0 ? "+" : ""}{review.results.net_bb} bb</b>
              <small>{review.results.bb_per_100 === null ? "no known results" : `${review.results.bb_per_100} bb/100`}</small></li>
            <li><small>SHOWDOWNS</small><b>{review.results.showdowns}</b><small>{review.results.showdowns_with_known_result} with opponent cards entered</small></li>
            {Object.entries(review.stats).map(([name, stat]) => (
              <li key={name}><small>{(STAT_NAMES[name] ?? name).toUpperCase()}</small><b>{percent(stat.frequency)}</b>
                <small>{stat.opportunities} chances · {stat.confidence.replace("_", " ")} confidence</small></li>
            ))}
          </ul>
          <p className="muted"><small>{review.results.note}{review.results.skipped_hands > 0 && ` ${review.results.skipped_hands} stored hand(s) could not be replayed and were skipped.`}</small></p>

          <h3>Possible leaks</h3>
          {review.leaks.length === 0 && <p className="muted">Nothing stands out. Flags need at least 20 chances for a statistic, so small samples show none.</p>}
          {review.leaks.map((leak) => (
            <div key={`${leak.stat}-${leak.issue}`} className="coach-leak">
              <strong>{leak.issue}</strong> <small>({percent(leak.frequency)} over {leak.opportunities} chances, {leak.confidence.replace("_", " ")} confidence)</small>
              <p>{leak.advice}</p>
            </div>
          ))}
          <p className="muted"><small>These are rule-of-thumb study prompts for heads-up play, not solver verdicts.</small></p>

          {review.by_opponent.length > 1 && (
            <>
              <h3>By opponent</h3>
              <ul>{review.by_opponent.map((row) => (
                <li key={row.opponent}>{row.opponent}: {row.hands} hands, {row.net_bb >= 0 ? "+" : ""}{row.net_bb} bb over {row.known_hands} with known results</li>
              ))}</ul>
            </>
          )}
        </>
      )}
    </div>
  );
}
