import { useEffect, useLayoutEffect, useState } from "react";

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
  /** Listen for typed cards (rank then suit, e.g. "a" "s") anywhere on the page. Only one input should listen at a time. */
  keyboard?: boolean;
};

/** Keys that start a card: ranks, plus "1"/"0" for a ten ("10"). */
const RANK_KEYS: Record<string, string> = Object.fromEntries([
  ...RANKS.map((rank) => [rank, rank]), ["1", "T"], ["0", "T"],
]);

/** True when a key press belongs to a text field rather than to the page-wide shortcuts. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return !!element && (["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName) || element.isContentEditable);
}

/** Short display name for a card, e.g. "A♠" or "10♥". */
export function shortCard(card: string): string {
  return `${card[0] === "T" ? "10" : card[0]}${SUIT_SYMBOL[card[1]] ?? card[1]}`;
}

/**
 * Click-to-pick card entry: a row of slots and the 52-card deck below it.
 * Clicking a deck card fills the active slot and moves to the next empty one;
 * clicking a filled slot selects it so the next pick replaces it.
 */
export function CardInput({ label, slots, cards, onChange, usedCards, limit = slots.length, keyboard = false }: Props) {
  // `cards` is always a dense list; the next empty slot is cards.length.
  const nextEmpty = (count: number) => (count < Math.min(limit, slots.length) ? count : null);
  const [active, setActive] = useState<number | null>(() => nextEmpty(cards.length));
  const [pendingRank, setPendingRank] = useState<string | null>(null);
  const [flash, setFlash] = useState("");
  const filled = cards.length;

  // Layout effect: the listener is in place before the next key press, even when keys arrive in a fast burst.
  useLayoutEffect(() => {
    if (!keyboard) { setPendingRank(null); return; }
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      const key = event.key;
      if (key === "Backspace" || key === "Escape") {
        if (pendingRank) { event.preventDefault(); setPendingRank(null); return; }
        if (key === "Backspace" && cards.length > 0) { event.preventDefault(); remove(cards.length - 1); setFlash(""); }
        return;
      }
      const suit = key.toLowerCase();
      if (pendingRank && (SUITS as readonly string[]).includes(suit)) {
        event.preventDefault();
        const card = pendingRank + suit;
        setPendingRank(null);
        if (cards.includes(card)) { setFlash(`${shortCard(card)} is already picked.`); return; }
        if (usedCards.has(card)) { setFlash(`${shortCard(card)} is already in use in this hand.`); return; }
        if (active === null) return;
        setFlash("");
        pick(card);
        return;
      }
      // "10": the "0" after a "1" just confirms the ten.
      if (key === "0" && pendingRank === "T") { event.preventDefault(); return; }
      const rank = RANK_KEYS[key.toUpperCase()];
      if (rank && active !== null) { event.preventDefault(); setPendingRank(rank); setFlash(""); }
    }
    // Capture phase, so the card being typed wins over page shortcuts that share keys (A, C, Backspace).
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

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
                  className={`deck-card suit-${suit}${chosen ? " is-chosen" : ""}${pendingRank === rank && !unavailable ? " is-pending" : ""}`}
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
      {keyboard && active !== null && (
        <p className="card-type-hint" aria-live="polite">
          {pendingRank
            ? <><b>{pendingRank === "T" ? "10" : pendingRank}</b> … now the suit: <kbd>s</kbd> <kbd>h</kbd> <kbd>d</kbd> <kbd>c</kbd></>
            : <>Or type it: rank then suit, e.g. <kbd>A</kbd><kbd>s</kbd> <kbd>T</kbd><kbd>d</kbd>{filled > 0 && <> · <kbd>⌫</kbd> removes the last card</>}</>}
          {flash && <span className="card-type-flash"> {flash}</span>}
        </p>
      )}
      {active === null && filled > 0 && <p className="muted card-done">Select a card above to change it.</p>}
    </fieldset>
  );
}
