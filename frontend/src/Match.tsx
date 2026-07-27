import { FormEvent, useState } from "react";
import type {
  BotName,
  MatchHandSummary,
  MatchRequest,
  MatchResponse,
} from "./types";

type MatchForm = {
  bot_a: BotName;
  bot_b: BotName;
  starting_stack: string;
  small_blind: string;
  big_blind: string;
  max_hands: string;
  seed: string;
  equity_iterations: "500" | "1000" | "2000";
};

const DEFAULT_FORM: MatchForm = {
  bot_a: "random",
  bot_b: "random",
  starting_stack: "10000",
  small_blind: "50",
  big_blind: "100",
  max_hands: "100",
  seed: "0",
  equity_iterations: "1000",
};

const BOTS: BotName[] = ["random", "tight", "aggressive", "equity"];

function parseInteger(value: string, label: string): number {
  if (!/^-?\d+$/.test(value.trim())) {
    throw new Error(`${label} must be a whole number.`);
  }
  return Number(value);
}

function validatedRequest(form: MatchForm): MatchRequest {
  const startingStack = parseInteger(form.starting_stack, "Starting stack");
  const smallBlind = parseInteger(form.small_blind, "Small blind");
  const bigBlind = parseInteger(form.big_blind, "Big blind");
  const maxHands = parseInteger(form.max_hands, "Maximum hands");
  const seed = parseInteger(form.seed, "Seed");
  const equityIterations = parseInteger(
    form.equity_iterations,
    "Equity iterations",
  );

  if (startingStack <= 0) throw new Error("Starting stack must be positive.");
  if (smallBlind <= 0) throw new Error("Small blind must be positive.");
  if (bigBlind <= 0) throw new Error("Big blind must be positive.");
  if (smallBlind > bigBlind) {
    throw new Error("Small blind cannot exceed the big blind.");
  }
  if (maxHands < 1 || maxHands > 10_000) {
    throw new Error("Maximum hands must be between 1 and 10,000.");
  }
  if (![500, 1000, 2000].includes(equityIterations)) {
    throw new Error("Equity iterations must be 500, 1,000, or 2,000.");
  }

  return {
    bot_a: form.bot_a,
    bot_b: form.bot_b,
    starting_stack: startingStack,
    small_blind: smallBlind,
    big_blind: bigBlind,
    max_hands: maxHands,
    seed,
    equity_iterations: equityIterations as 500 | 1000 | 2000,
  };
}

function apiError(body: unknown): string {
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    Array.isArray(body.detail) &&
    body.detail[0] &&
    typeof body.detail[0] === "object" &&
    "msg" in body.detail[0] &&
    typeof body.detail[0].msg === "string"
  ) {
    return body.detail[0].msg;
  }
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  return "The match could not be completed. Check the inputs and try again.";
}

function signed(value: number): string {
  return value > 0 ? `+${value.toLocaleString()}` : value.toLocaleString();
}

function playerLabel(player: "a" | "b"): string {
  return player === "a" ? "Bot A" : "Bot B";
}

function winnerLabel(winner: MatchResponse["winner"]): string {
  return winner === "tied" ? "Tied" : winner;
}

function terminationLabel(
  terminationReason: MatchResponse["termination_reason"],
): string {
  return terminationReason === "hand_limit" ? "Hand limit" : "Elimination";
}

function endingLabel(hand: MatchHandSummary): string {
  return hand.showdown ? "Showdown" : hand.fold_ended ? "Fold" : "Other";
}

function fallbackLabel(hand: MatchHandSummary): string {
  if (!hand.fallback_diagnostics.length) return "None";
  return hand.fallback_diagnostics
    .map((diagnostic) =>
      typeof diagnostic.reason === "string"
        ? diagnostic.reason
        : JSON.stringify(diagnostic),
    )
    .join("; ");
}

export default function Match() {
  const [form, setForm] = useState<MatchForm>(DEFAULT_FORM);
  const [result, setResult] = useState<MatchResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function update<K extends keyof MatchForm>(key: K, value: MatchForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;

    let request: MatchRequest;
    try {
      request = validatedRequest(form);
    } catch (validationError) {
      setError(
        validationError instanceof Error
          ? validationError.message
          : "Check the match inputs.",
      );
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch("/api/matches/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiError(body));
      setResult(body as MatchResponse);
    } catch (requestError) {
      setError(
        requestError instanceof TypeError
          ? "The backend is unavailable. Start it and try the match again."
          : requestError instanceof Error
            ? requestError.message
            : "The match could not be completed.",
      );
    } finally {
      setLoading(false);
    }
  }

  const chipConserved = result
    ? result.final_stack_a + result.final_stack_b === result.starting_stack * 2
    : false;
  const netZero = result
    ? result.bot_a_net_chips + result.bot_b_net_chips === 0
    : false;

  return (
    <section className="panel match-panel">
      <h1>Persistent Match</h1>
      <p>
        Play a heads-up match where stacks carry forward from hand to hand until
        one bot is eliminated or the hand limit is reached. For independent
        hands with a fresh stack each time, use the Simulator tab.
      </p>

      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Bot A
            <select
              value={form.bot_a}
              onChange={(event) =>
                update("bot_a", event.target.value as BotName)
              }
            >
              {BOTS.map((bot) => (
                <option key={bot} value={bot}>
                  {bot}
                </option>
              ))}
            </select>
          </label>
          <label>
            Bot B
            <select
              value={form.bot_b}
              onChange={(event) =>
                update("bot_b", event.target.value as BotName)
              }
            >
              {BOTS.map((bot) => (
                <option key={bot} value={bot}>
                  {bot}
                </option>
              ))}
            </select>
          </label>
          <label>
            Starting stack
            <input
              inputMode="numeric"
              value={form.starting_stack}
              onChange={(event) => update("starting_stack", event.target.value)}
            />
          </label>
          <label>
            Small blind
            <input
              inputMode="numeric"
              value={form.small_blind}
              onChange={(event) => update("small_blind", event.target.value)}
            />
          </label>
          <label>
            Big blind
            <input
              inputMode="numeric"
              value={form.big_blind}
              onChange={(event) => update("big_blind", event.target.value)}
            />
          </label>
          <label>
            Maximum hands
            <input
              inputMode="numeric"
              value={form.max_hands}
              onChange={(event) => update("max_hands", event.target.value)}
            />
          </label>
          <label>
            Seed
            <input
              inputMode="numeric"
              value={form.seed}
              onChange={(event) => update("seed", event.target.value)}
            />
          </label>
          <label>
            Equity iterations
            <select
              value={form.equity_iterations}
              onChange={(event) =>
                update(
                  "equity_iterations",
                  event.target.value as MatchForm["equity_iterations"],
                )
              }
            >
              <option value="500">500</option>
              <option value="1000">1,000</option>
              <option value="2000">2,000</option>
            </select>
          </label>
        </div>
        <button type="submit" disabled={loading}>
          {loading ? "Running persistent match…" : "Run persistent match"}
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="result match-result" aria-live="polite">
          <div className="result-heading">
            <div>
              <h2>Match result</h2>
              <p>
                {result.bot_a} vs {result.bot_b} · seed {result.seed}
              </p>
            </div>
            <span className="termination-badge">
              {winnerLabel(result.winner)} ·{" "}
              {terminationLabel(result.termination_reason)}
            </span>
          </div>

          <div className="metrics">
            <div>
              <span>Match ID</span>
              <strong>{result.match_id}</strong>
            </div>
            <div>
              <span>Bot A / Bot B</span>
              <strong>
                {result.bot_a} / {result.bot_b}
              </strong>
            </div>
            <div>
              <span>Seed</span>
              <strong>{result.seed}</strong>
            </div>
            <div>
              <span>Starting stack</span>
              <strong>{result.starting_stack.toLocaleString()}</strong>
            </div>
            <div>
              <span>Blinds</span>
              <strong>
                {result.small_blind.toLocaleString()} /{" "}
                {result.big_blind.toLocaleString()}
              </strong>
            </div>
            <div>
              <span>Maximum hands</span>
              <strong>{result.max_hands.toLocaleString()}</strong>
            </div>
            <div>
              <span>Hands played</span>
              <strong>{result.hands_played.toLocaleString()}</strong>
            </div>
            <div>
              <span>Winner / termination</span>
              <strong>
                {winnerLabel(result.winner)} /{" "}
                {terminationLabel(result.termination_reason)}
              </strong>
            </div>
            <div>
              <span>Final Bot A stack</span>
              <strong>{result.final_stack_a.toLocaleString()}</strong>
            </div>
            <div>
              <span>Final Bot B stack</span>
              <strong>{result.final_stack_b.toLocaleString()}</strong>
            </div>
            <div>
              <span>Bot A net</span>
              <strong className={result.bot_a_net_chips >= 0 ? "positive" : "negative"}>
                {signed(result.bot_a_net_chips)}
              </strong>
            </div>
            <div>
              <span>Bot B net</span>
              <strong className={result.bot_b_net_chips >= 0 ? "positive" : "negative"}>
                {signed(result.bot_b_net_chips)}
              </strong>
            </div>
            <div>
              <span>Showdowns / folds</span>
              <strong>
                {result.showdowns} / {result.fold_ended_hands}
              </strong>
            </div>
            <div>
              <span>Illegal actions</span>
              <strong>{result.illegal_actions}</strong>
            </div>
            <div>
              <span>Fallback diagnostics</span>
              <strong>{result.fallback_diagnostics}</strong>
            </div>
          </div>

          <div className="invariant-grid">
            <p className={chipConserved ? "invariant-pass" : "invariant-fail"}>
              Chip conservation: {chipConserved ? "Pass" : "Warning"}
            </p>
            <p className={netZero ? "invariant-pass" : "invariant-fail"}>
              Net zero-sum: {netZero ? "Pass" : "Warning"}
            </p>
          </div>

          <h2>Hand summaries</h2>
          <div className="table-wrap" tabIndex={0} aria-label="Scrollable hand summaries">
            <table>
              <thead>
                <tr>
                  <th>Hand</th>
                  <th>Positions</th>
                  <th>Start A</th>
                  <th>Start B</th>
                  <th>End A</th>
                  <th>End B</th>
                  <th>Winner</th>
                  <th>Net A</th>
                  <th>Net B</th>
                  <th>Ending</th>
                  <th>Board</th>
                  <th>Illegal</th>
                  <th>Fallbacks</th>
                  <th>Settled</th>
                </tr>
              </thead>
              <tbody>
                {result.hand_summaries.map((hand) => (
                  <tr key={hand.hand_number}>
                    <td>{hand.hand_number}</td>
                    <td>
                      BTN {playerLabel(hand.button_player)} · SB{" "}
                      {playerLabel(hand.small_blind_player)} · BB{" "}
                      {playerLabel(hand.big_blind_player)}
                    </td>
                    <td>{hand.starting_stack_a.toLocaleString()}</td>
                    <td>{hand.starting_stack_b.toLocaleString()}</td>
                    <td>{hand.ending_stack_a.toLocaleString()}</td>
                    <td>{hand.ending_stack_b.toLocaleString()}</td>
                    <td>{winnerLabel(hand.winner)}</td>
                    <td className={hand.net_chips_a >= 0 ? "positive" : "negative"}>
                      {signed(hand.net_chips_a)}
                    </td>
                    <td className={hand.net_chips_b >= 0 ? "positive" : "negative"}>
                      {signed(hand.net_chips_b)}
                    </td>
                    <td>{endingLabel(hand)}</td>
                    <td>
                      {hand.board.length ? (
                        hand.board.map((card) => (
                          <span className="card-token" key={card}>
                            {card}
                          </span>
                        ))
                      ) : (
                        <span className="muted">No board cards</span>
                      )}
                    </td>
                    <td>{hand.illegal_actions}</td>
                    <td>{fallbackLabel(hand)}</td>
                    <td>{hand.settlement_complete ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}
