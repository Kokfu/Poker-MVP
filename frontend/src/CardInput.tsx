import { useEffect, useState } from "react";

const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SUITS = ["s", "h", "d", "c"] as const;
export const SUIT_SYMBOL: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };
const SUIT_NAME: Record<string, string> = { s: "spades", h: "hearts", d: "diamonds", c: "clubs" };
const RANK_NAME: Record<string, string> = {
  A: "ace", K: "king", Q: "queen", J: "jack", T: "ten", "9": "nine", "8": "eight",
  "7": "seven", "6": "six", "5": "five", "4": "four", "3": "three", "2": "two",
};

export function cardName(card: string): string {
  return `${RANK_NAME[card[0]] ?? card[0]} of ${SUIT_NAME[card[1]] ?? card[1]}`;
}

/** A small face-up card in the four-colour deck most online rooms use. */
export function PlayingCard({ card, size = "md" }: { card: string; size?: "sm" | "md" }) {
  return (
    <span className={`pcard pcard-${size} suit-${card[1]}`} role="img" aria-label={cardName(card)}>
      <span className="pcard-rank">{card[0] === "T" ? "10" : card[0]}</span>
      <span className="pcard-suit" aria-hidden="true">{SUIT_SYMBOL[card[1]]}</span>
    </span>
  );
}

type Props = {
  label: string;
  /** One label per slot, e.g. ["Card 1", "Card 2"] or ["Flop", "Flop", "Flop", "Turn", "River"]. */
  slots: string[];
  cards: string[];
  onChange: (cards: string[]) => void;
  /** Cards already used elsewhere (hero, board, shown cards); they cannot be picked here. */
  usedCards: Set<string>;
  /** Only the first `limit` slots are open (e.g. the board before the turn is known). */
  limit?: number;
};

/**
 * Click-to-pick card entry: a row of slots and the 52-card deck below it.
 * Clicking a deck card fills the active slot and moves to the next empty one;
 * clicking a filled slot selects it so the next pick replaces it.
 */
export function CardInput({ label, slots, cards, onChange, usedCards, limit = slots.length }: Props) {
  // `cards` is always a dense list; the next empty slot is cards.length.
  const nextEmpty = (count: number) => (count < Math.min(limit, slots.length) ? count : null);
  const [active, setActive] = useState<number | null>(() => nextEmpty(cards.length));
  const filled = cards.length;

  useEffect(() => {
    // Keep the active slot valid when cards change from outside (new hand, loaded hand, Clear).
    setActive((current) => (current !== null && current < cards.length && current < limit ? current : nextEmpty(cards.length)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards.join(","), limit]);

  function pick(card: string) {
    const existing = cards.indexOf(card);
    if (existing !== -1) { remove(existing); return; }
    if (active === null) return;
    const next = [...cards];
    if (active < next.length) next[active] = card;
    else next.push(card);
    onChange(next);
    setActive(nextEmpty(next.length));
  }

  function remove(index: number) {
    const next = cards.filter((_, i) => i !== index);
    onChange(next);
    setActive(nextEmpty(next.length));
  }

  return (
    <fieldset className="card-input">
      <legend>{label}</legend>
      <div className="card-slots">
        {slots.map((slotLabel, index) => {
          const card = cards[index];
          const locked = index >= limit;
          return (
            <div key={index} className="card-slot-wrap">
              <button
                type="button"
                className={`card-slot${active === index ? " is-active" : ""}${card ? " is-filled" : ""}`}
                disabled={locked || (!card && index !== cards.length)}
                aria-label={card ? `${slotLabel}: ${cardName(card)}. Click to replace` : `${slotLabel}: empty`}
                aria-pressed={active === index}
                onClick={() => setActive(index)}
              >
                {card ? <PlayingCard card={card} /> : <span className="card-slot-empty">{locked ? "" : "+"}</span>}
              </button>
              <span className="card-slot-label">{slotLabel}</span>
              {card && (
                <button type="button" className="card-slot-clear" aria-label={`Remove ${cardName(card)}`} onClick={() => remove(index)}>
                  <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
                </button>
              )}
            </div>
          );
        })}
        {filled > 0 && (
          <button type="button" className="link-button card-clear-all" onClick={() => { onChange([]); setActive(nextEmpty(0)); }}>
            Clear
          </button>
        )}
      </div>
      {active !== null && <div className="deck-grid" role="group" aria-label={`Pick ${label.toLowerCase()}`}>
        {SUITS.map((suit) => (
          <div key={suit} className="deck-row">
            {RANKS.map((rank) => {
              const card = rank + suit;
              const chosen = cards.includes(card);
              const unavailable = !chosen && usedCards.has(card);
              return (
                <button
                  key={card}
                  type="button"
                  className={`deck-card suit-${suit}${chosen ? " is-chosen" : ""}`}
                  disabled={unavailable}
                  aria-pressed={chosen}
                  aria-label={cardName(card)}
                  onClick={() => pick(card)}
                >
                  <span>{rank === "T" ? "10" : rank}</span>
                  <span aria-hidden="true">{SUIT_SYMBOL[suit]}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>}
      {active === null && filled > 0 && <p className="muted card-done">Select a card above to change it.</p>}
    </fieldset>
  );
}
