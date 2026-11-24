import { useState } from "react";
import { AnalysisResults } from "./components/AnalysisResults";
import { CardSelector } from "./components/CardSelector";
import { DeckVisualizer } from "./components/DeckVisualizer";
import { InputForm } from "./components/InputForm";
import { Simulator } from "./components/Simulator";
import Coach from "./Coach";
import Match from "./Match";
import Replay from "./Replay";
import type { Analysis } from "./types";

type Tab = "analyzer" | "coach" | "simulator" | "match" | "replay";
const TABS: [Tab, string][] = [["coach", "Coach"], ["analyzer", "Equity calculator"], ["simulator", "Bot simulator"], ["match", "Bot match"], ["replay", "Replay"]];

export default function App() {
  const [tab, setTab] = useState<Tab>("coach");
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
      <header className="app-header">
        <div>
          <h1>Poker Coach</h1>
          <p>Texas Hold’em study tool. Enter your cards, get advice, and learn how your opponents play.</p>
        </div>
        <p className="app-note">Manual entry only. No site automation, no real-money play.</p>
      </header>
      <nav className="app-nav" aria-label="Poker tools">
        {TABS.map(([item, label]) => (
          <button key={item} type="button" aria-current={tab === item ? "page" : undefined} className={tab === item ? "is-on" : ""} onClick={() => setTab(item)}>
            {label}
          </button>
        ))}
      </nav>

      {tab === "coach" ? <Coach /> : tab === "replay" ? <Replay /> : tab === "match" ? (
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
            className="analyze primary"
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
