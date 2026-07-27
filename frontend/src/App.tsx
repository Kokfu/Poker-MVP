import { useState } from "react";
import { AnalysisResults } from "./components/AnalysisResults";
import { CardSelector } from "./components/CardSelector";
import { DeckVisualizer } from "./components/DeckVisualizer";
import { InputForm } from "./components/InputForm";
import { Simulator } from "./components/Simulator";
import Match from "./Match";
import type { Analysis } from "./types";

type Tab = "analyzer" | "simulator" | "match";

export default function App() {
  const [tab, setTab] = useState<Tab>("analyzer");
  const [cards, setCards] = useState<(string | null)[]>(Array(7).fill(null));
  const [form, setForm] = useState({
    pot: "100",
    amount_to_call: "40",
    hero_stack: "850",
    iterations: "50000",
    position: "",
    action_history: "",
  });
  const [result, setResult] = useState<Analysis>();
  const [error, setError] = useState("");

  async function analyze() {
    setError("");
    if (!cards[0] || !cards[1]) {
      setError("Select both hero cards.");
      return;
    }
    const board = cards.slice(2).filter(Boolean) as string[];
    if (![0, 3, 4, 5].includes(board.length)) {
      setError("Board needs 0, 3, 4, or 5 cards.");
      return;
    }
    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hero_cards: cards.slice(0, 2),
          board_cards: board,
          opponents: 1,
          pot: +form.pot,
          amount_to_call: +form.amount_to_call,
          hero_stack: +form.hero_stack,
          iterations: +form.iterations,
          position: form.position || null,
          action_history: form.action_history || null,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail?.[0]?.msg || "Analysis failed");
      }
      setResult(body);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Analysis failed",
      );
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">LOCAL EDUCATIONAL TOOL</p>
        <h1>Poker Analyzer MVP</h1>
        <p>Texas Hold’em analysis from manually entered cards.</p>
      </header>
      <aside>
        Manual input only · No website automation · No real-money play · No
        hidden-card access
      </aside>
      <nav aria-label="Poker tools">
        {(["analyzer", "simulator", "match"] as Tab[]).map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={tab === item}
            onClick={() => setTab(item)}
          >
            {item === "analyzer"
              ? "Analyzer"
              : item === "simulator"
                ? "Simulator"
                : "Match"}
          </button>
        ))}
      </nav>

      {tab === "match" ? (
        <Match />
      ) : tab === "simulator" ? (
        <Simulator />
      ) : (
        <>
          <div className="grid">
            <CardSelector cards={cards} setCards={setCards} />
            <InputForm form={form} setForm={setForm} />
          </div>
          <DeckVisualizer />
          {error && <p className="error">{error}</p>}
          <button
            className="analyze"
            onClick={analyze}
            disabled={!cards[0] || !cards[1]}
          >
            Analyze hand
          </button>
          {result && <AnalysisResults data={result} />}
        </>
      )}
    </main>
  );
}
