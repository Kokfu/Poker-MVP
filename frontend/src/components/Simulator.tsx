import { useState } from "react";

type Result = {
  hands_played: number;
  seed: number;
  duration_ms: number;
  bot_a_wins: number;
  bot_b_wins: number;
  ties: number;
  bot_a_net_chips: number;
  bot_b_net_chips: number;
  bot_a_bb_per_100: number;
  bot_b_bb_per_100: number;
  showdowns: number;
  fold_ended_hands: number;
  illegal_actions: number;
  action_counts: Record<string, Record<string, number>>;
};

export function Simulator() {
  const [values, setValues] = useState({
    bot_a: "random",
    bot_b: "aggressive",
    hands: "100",
    seed: "42",
    starting_stack_bb: "100",
    equity_iterations: "1000",
  });
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function set(key: string, value: string) {
    setValues({ ...values, [key]: value });
  }

  async function run() {
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/simulations/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...values,
          hands: +values.hands,
          seed: +values.seed,
          starting_stack_bb: +values.starting_stack_bb,
          equity_iterations: +values.equity_iterations,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail?.[0]?.msg || "Simulation failed");
      }
      setResult(body);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Network error",
      );
    } finally {
      setLoading(false);
    }
  }

  const bots = ["random", "tight", "aggressive", "equity"];

  return (
    <>
      <section>
        <h2>Independent Hand Simulator</h2>
        <p className="muted">
          Run local-only heads-up hands with both stacks reset before every
          hand. Equity iterations trade speed for precision.
        </p>
        <div className="grid">
          <label>
            Bot A
            <select
              value={values.bot_a}
              onChange={(event) => set("bot_a", event.target.value)}
            >
              {bots.map((bot) => (
                <option key={bot}>{bot}</option>
              ))}
            </select>
          </label>
          <label>
            Bot B
            <select
              value={values.bot_b}
              onChange={(event) => set("bot_b", event.target.value)}
            >
              {bots.map((bot) => (
                <option key={bot}>{bot}</option>
              ))}
            </select>
          </label>
          <label>
            Hands
            <select
              value={values.hands}
              onChange={(event) => set("hands", event.target.value)}
            >
              {[100, 1000, 10000].map((hands) => (
                <option key={hands}>{hands}</option>
              ))}
            </select>
          </label>
          <label>
            Seed
            <input
              type="number"
              value={values.seed}
              onChange={(event) => set("seed", event.target.value)}
            />
          </label>
          <label>
            Starting stack BB
            <input
              type="number"
              min="10"
              max="500"
              value={values.starting_stack_bb}
              onChange={(event) => set("starting_stack_bb", event.target.value)}
            />
          </label>
          <label>
            Equity iterations
            <select
              value={values.equity_iterations}
              onChange={(event) =>
                set("equity_iterations", event.target.value)
              }
            >
              {[500, 1000, 2000].map((iterations) => (
                <option key={iterations}>{iterations}</option>
              ))}
            </select>
          </label>
        </div>
        <button className="analyze" disabled={loading} onClick={run}>
          {loading ? "Running…" : "Run Simulation"}
        </button>
        {error && <p className="error">{error}</p>}
      </section>
      {result && (
        <section className="results">
          <h2>Simulation results</h2>
          <div className="metrics">
            <p>
              <small>Hands / seed</small>
              {result.hands_played} / {result.seed}
            </p>
            <p>
              <small>Runtime</small>
              {result.duration_ms.toFixed(1)} ms
            </p>
            <p>
              <small>A wins / B wins / ties</small>
              {result.bot_a_wins} / {result.bot_b_wins} / {result.ties}
            </p>
            <p>
              <small>A / B BB per 100</small>
              {result.bot_a_bb_per_100.toFixed(2)} /{" "}
              {result.bot_b_bb_per_100.toFixed(2)}
            </p>
            <p>
              <small>A / B net chips</small>
              {result.bot_a_net_chips} / {result.bot_b_net_chips}
            </p>
            <p>
              <small>Showdowns / folds</small>
              {result.showdowns} / {result.fold_ended_hands}
            </p>
            <p>
              <small>Illegal actions</small>
              {result.illegal_actions}
            </p>
          </div>
        </section>
      )}
    </>
  );
}
