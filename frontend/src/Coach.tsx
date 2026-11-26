import { FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import CoachReview from "./CoachReview";
import CoachData from "./CoachData";
import CoachMultiway from "./CoachMultiway";
import { CardInput, PlayingCard, isTypingTarget } from "./CardInput";
import { AdvicePrefetch } from "./AdvicePrefetch";

type Actor = "hero" | "villain";
type ActionKind = "fold" | "check" | "call" | "bet" | "raise" | "all_in";
type SpotAction = { actor: Actor; action: ActionKind; amount?: number | null };

type SpotState = {
  street: string;
  pot: number;
  to_call: number;
  legal_actions: ActionKind[];
  minimum_target: number | null;
  maximum_target: number;
  hero_stack: number;
  villain_stack: number;
  board: string[];
};

type Explanation = {
  source: string;
  hero_equity_vs_range?: number;
  villain_effective_combos?: number;
  villain_top_classes?: { hand: string; share: number }[];
  villain_range_makeup?: { type: string; share: number }[];
  exploit?: { active: boolean; hands_observed?: number; classification?: string; locked_nodes?: number };
  reason?: string;
};

type Explain = {
  chosen: string | null;
  frequency: number | null;
  ev: number | null;
  ev_note?: string;
  equity?: number | null;
  options: { label: string; frequency: number; ev?: number }[];
  opponent_range: { effective_combos: number } | null;
  reason: string;
};

export function CoachStrategy({ options }: { options: Explain["options"] }) {
  if (options.length === 0) return null;
  return (
    <div className="coach-strategy">
      {options.map(({ label, frequency, ev }) => (
        <div key={label} className="coach-bar">
          <span>{describeLabel(label)}</span>
          <div><i style={{ width: `${Math.round(frequency * 100)}%` }} /></div>
          <b>{Math.round(frequency * 100)}%</b>
          {ev !== undefined && <small className="coach-ev" title="Chips you expect to win from here on, counting only chips still to put in (fold = 0)">EV {ev >= 0 ? "+" : ""}{Math.round(ev)}</small>}
        </div>
      ))}
    </div>
  );
}

type StatRead = { frequency: number; opportunities: number; confidence: string };
type Profile = {
  hands_observed: number;
  classification: string;
  label?: { type: string; confidence: string; hands: number; decisions: number; assigned: boolean };
  preflop: Record<string, StatRead>;
  postflop: Record<string, Record<string, StatRead>>;
};

type CoachResponse =
  | { status: "hero_to_act"; advice: { action: ActionKind; amount: number | null }; explanation: Explanation; explain: Explain | null; state: SpotState; exploiting: boolean; adjusted?: boolean; opponent_profile: Profile | null }
  | { status: "villain_to_act"; state: SpotState }
  | { status: "need_board"; street: string; cards_needed: number; pot?: number }
  | { status: "hand_complete"; summary: { showdown: boolean; board: string[]; hero_net?: number } };

type QuickAdvice = { status: "quick"; advice: { action: ActionKind }; reason: string; state: SpotState };

export async function requestCoachAdvice(input: RequestInit, onQuick?: (preview: QuickAdvice) => void): Promise<CoachResponse> {
  let fullFinished = false;
  if (onQuick) {
    const previewRequest = fetch("/api/coach/advise/quick", input).then(async (response) => {
      const preview: QuickAdvice | null = response.ok ? await response.json() : null;
      if (!fullFinished && !input.signal?.aborted && preview?.status === "quick") onQuick(preview);
    }).catch(() => { /* The full request supplies the advice. */ });
    // Let a fast preview arrive before starting the CPU-heavy solve, but cap the wait.
    let headStart: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([previewRequest, new Promise<void>((resolve) => { headStart = setTimeout(resolve, 50); })]);
    clearTimeout(headStart);
  }
  try {
    input.signal?.throwIfAborted();
    const response = await fetch("/api/coach/advise", input);
    const body = await response.json();
    if (!response.ok) throw new Error(describeError(body, "Coach request failed"));
    return body;
  } finally {
    fullFinished = true;
  }
}

type RawSpot = {
  hero_cards: string[];
  board: string[];
  hero_position: "button" | "big_blind";
  small_blind: number;
  big_blind: number;
  hero_stack: number;
  villain_stack: number;
  actions: SpotAction[];
  villain_cards: string[] | null;
};

type HandRecord = { id: number; created_at: string; spot: RawSpot; result?: { showdown: boolean; hero_net: number | null } | null };

const ACTION_TEXT: Record<ActionKind, string> = { fold: "Fold", check: "Check", call: "Call", bet: "Bet", raise: "Raise to", all_in: "All-in" };
const STAT_TEXT: Record<string, string> = {
  vpip: "Plays hand (VPIP)", preflop_raise: "Raises preflop", limp: "Limps", three_bet: "3-bets",
  fold_to_raise: "Folds to a raise", aggressive: "Aggression", bet: "Bets when checked to",
  fold_to_bet: "Folds to a bet", call_vs_bet: "Calls a bet", raise_vs_bet: "Raises a bet",
};

const OPPONENT_COUNTS = [1, 2, 3, 4, 5, 6, 7, 8];
const POSTFLOP_STREETS = ["flop", "turn", "river"] as const;
const ACTION_KEYS: Record<string, ActionKind[]> = { F: ["fold"], C: ["check", "call"], B: ["bet", "raise"], A: ["all_in"] };
const KEY_FOR_ACTION: Record<ActionKind, string> = { fold: "F", check: "C", call: "C", bet: "B", raise: "B", all_in: "A" };
const FIELD_LABELS: Record<string, string> = {
  small_blind: "Small blind", big_blind: "Big blind", hero_stack: "Your stack", villain_stack: "Villain stack",
  opponent: "Opponent name", hero_cards: "Your cards", board: "Board", villain_cards: "Villain's cards",
};

function describeError(body: { detail?: unknown } | null, fallback: string): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail) || detail.length === 0) return fallback;
  return detail.map((item: { loc?: (string | number)[]; msg?: string }) => {
    const path = (item.loc ?? []).slice(1);
    const message = (item.msg ?? "invalid value").replace(/^./, (letter) => letter.toLowerCase());
    let label: string;
    if (path[0] === "actions" && typeof path[1] === "number") label = `Action ${path[1] + 1}${path[2] === "amount" ? " amount" : ""}`;
    else label = FIELD_LABELS[String(path[0])] ?? path.join(".");
    return label ? `${label}: ${message}` : message;
  }).join("; ");
}

function describeLabel(label: string): string {
  const [kind, amount] = label.split("_");
  if (label === "all_in") return "All-in";
  if (amount) return `${kind === "bet" ? "Bet" : "Raise to"} ${amount}`;
  return kind[0].toUpperCase() + kind.slice(1);
}

function foldedText(actions: SpotAction[]): string {
  const last = actions[actions.length - 1];
  return last?.action === "fold" ? (last.actor === "hero" ? "You folded." : "Villain folded.") : "Someone folded.";
}

function describeAction(step: SpotAction): string {
  const who = step.actor === "hero" ? "You" : "Villain";
  return `${who}: ${ACTION_TEXT[step.action]}${step.amount ? ` ${step.amount}` : ""}`;
}

function effectiveMaximum(state: SpotState, actor: Actor): number {
  const actorStack = actor === "hero" ? state.hero_stack : state.villain_stack;
  const opponentStack = actor === "hero" ? state.villain_stack : state.hero_stack;
  const actorPosted = state.maximum_target - actorStack;
  const opponentCap = actorPosted + state.to_call + opponentStack;
  return Math.max(state.minimum_target ?? 0, Math.min(state.maximum_target, opponentCap));
}

function quickSizes(state: SpotState, actor: Actor): { label: string; amount: number }[] {
  const { pot, to_call, minimum_target } = state;
  const maximum_target = effectiveMaximum(state, actor);
  const actorStack = actor === "hero" ? state.hero_stack : state.villain_stack;
  const floor = minimum_target ?? 0;
  const currentHighestBet = state.maximum_target - actorStack + to_call;
  const clamp = (raw: number) => Math.min(maximum_target, Math.max(floor, Math.round(raw)));
  const fractions: [string, number][] = [["1/3 pot", 1 / 3], ["1/2 pot", 0.5], ["3/4 pot", 0.75], ["Pot", 1]];
  const sized = fractions.map(([label, fraction]) => ({
    label,
    amount: clamp(to_call > 0 ? currentHighestBet + fraction * (pot + 2 * to_call) : fraction * pot),
  }));
  return [...sized, { label: "All-in", amount: maximum_target }];
}

const STREET_NAMES = ["preflop", "flop", "turn", "river"];

/** The street of each action in a heads-up hand: a call closes the street (except a preflop limp), as do two checks or a check after a limp. */
export function actionStreets(actions: SpotAction[]): string[] {
  let street = 0;
  let checks = 0;
  return actions.map((action, index) => {
    const name = STREET_NAMES[Math.min(street, 3)];
    if (action.action === "call") {
      if (!(street === 0 && index === 0)) { street += 1; checks = 0; }
    } else if (action.action === "check") {
      checks += 1;
      if (street === 0 || checks === 2) { street += 1; checks = 0; }
    } else {
      checks = 0;
    }
    return name;
  });
}

export function recentVillainSize(history: HandRecord[], kind: "bet" | "raise", state: SpotState, bigBlind: number): number | undefined {
  if (!state.legal_actions.includes(kind) || state.minimum_target === null || bigBlind <= 0) return;
  const maximum = effectiveMaximum(state, "villain");
  for (const { spot } of history) {
    if (spot.big_blind <= 0) continue;
    // Only sizes from the same street: a river raise is no guide to a preflop raise.
    const streets = actionStreets(spot.actions);
    for (let index = spot.actions.length - 1; index >= 0; index -= 1) {
      const action = spot.actions[index];
      if (state.street && streets[index] !== state.street) continue;
      if (action.actor !== "villain" || action.action !== kind || action.amount == null) continue;
      const amount = Math.round(action.amount * bigBlind / spot.big_blind);
      if (amount >= state.minimum_target && amount <= maximum) return amount;
    }
  }
}

/** Table settings remembered between visits, so a new session starts where the last one left off. */
type Prefs = {
  blinds: { small: string; big: string };
  stacks: { hero: string; villain: string };
  opponent: string;
  exploit: boolean;
  players: number;
  autoContinue: boolean;
  autoSave: boolean;
  carryStacks: boolean;
  showDetails: boolean;
};
const PREFS_KEY = "coach.prefs.v1";

function loadPrefs(): Partial<Prefs> {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PREFS_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function blurFocus() {
  const focused = document.activeElement as HTMLElement | null;
  if (focused && focused !== document.body) focused.blur();
}

function defaultAmount(result: CoachResponse): string {
  if (result.status === "hero_to_act") return result.advice.amount ? String(result.advice.amount) : String(result.state.minimum_target ?? "");
  if (result.status === "villain_to_act") return String(result.state.minimum_target ?? "");
  return "";
}

export default function Coach() {
  const [prefs] = useState(loadPrefs);
  const [heroCards, setHeroCards] = useState<string[]>([]);
  const [handNumber, setHandNumber] = useState(0);
  const [logged, setLogged] = useState(false);
  const [position, setPosition] = useState<"button" | "big_blind">("button");
  const [blinds, setBlinds] = useState(prefs.blinds ?? { small: "50", big: "100" });
  const [stacks, setStacks] = useState(prefs.stacks ?? { hero: "10000", villain: "10000" });
  const [opponent, setOpponent] = useState(prefs.opponent ?? "");
  const [exploit, setExploit] = useState(prefs.exploit ?? true);
  const [autoContinue, setAutoContinue] = useState(prefs.autoContinue ?? true);
  const [autoSave, setAutoSave] = useState(prefs.autoSave ?? true);
  const [carryStacks, setCarryStacks] = useState(prefs.carryStacks ?? true);
  const [showDetails, setShowDetails] = useState(prefs.showDetails ?? false);
  const [board, setBoard] = useState<string[]>([]);
  const [boardDraft, setBoardDraft] = useState<string[]>([]);
  const [actions, setActions] = useState<SpotAction[]>([]);
  /** Earlier (actions, board) snapshots of this hand, newest last, so Undo can step back through cards too. */
  const [past, setPast] = useState<{ actions: SpotAction[]; board: string[] }[]>([]);
  const [amount, setAmount] = useState("");
  /** True once the user typed the bet size themselves, so digit keys append instead of replacing the suggestion. */
  const [typed, setTyped] = useState(false);
  const [villainCards, setVillainCards] = useState<string[]>([]);
  const [result, setResult] = useState<CoachResponse>();
  const [quick, setQuick] = useState<QuickAdvice & { actions: SpotAction[] }>();
  const [reviewMode, setReviewMode] = useState(false);
  const [view, setView] = useState<"play" | "review" | "data">("play");
  const [players, setPlayers] = useState(prefs.players ?? 1);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [opponents, setOpponents] = useState<{ name: string; hands: number }[]>([]);
  const [loadedHistory, setHistory] = useState<{ name: string; hands: HandRecord[] }>();
  const historyRequest = useRef(0);
  const profileRequest = useRef(0);
  const opponentsRequest = useRef(0);
  const selectedOpponent = useRef(opponent.trim());
  const adviceRequest = useRef<AbortController | undefined>(undefined);
  const [prefetch] = useState(() => new AdvicePrefetch());
  const history = loadedHistory?.name === opponent.trim() ? loadedHistory.hands : [];
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deletingOpponent, setDeletingOpponent] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const spot = useMemo(() => ({
    hero_cards: heroCards, board, hero_position: position,
    small_blind: +blinds.small, big_blind: +blinds.big, hero_stack: +stacks.hero, villain_stack: +stacks.villain, actions,
  }), [heroCards, board, position, blinds, stacks, actions]);

  async function loadOpponents() {
    const request = ++opponentsRequest.current;
    try {
      const response = await fetch("/api/coach/opponents");
      if (!response.ok) return;
      const opponents = await response.json();
      if (request === opponentsRequest.current) setOpponents(opponents);
    } catch { /* the list is optional */ }
  }

  async function loadProfile(name: string) {
    const cleaned = name.trim();
    if (cleaned !== selectedOpponent.current) return;
    const request = ++profileRequest.current;
    if (!cleaned) { setProfile(null); return; }
    try {
      const response = await fetch(`/api/coach/opponents/${encodeURIComponent(cleaned)}`);
      const profile = response.ok ? (await response.json()).profile : null;
      if (request === profileRequest.current) setProfile(profile);
    } catch {
      if (request === profileRequest.current) setProfile(null);
    }
  }

  async function loadHistory(name: string) {
    const cleaned = name.trim();
    if (cleaned !== selectedOpponent.current) return;
    const request = ++historyRequest.current;
    if (!cleaned) { setHistory(undefined); setHistoryLoading(false); return; }
    setHistoryLoading(true); setHistoryError("");
    try {
      const response = await fetch(`/api/coach/opponents/${encodeURIComponent(cleaned)}/hands`);
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load hand history");
      if (request === historyRequest.current) setHistory({ name: cleaned, hands: body });
    } catch (requestError) {
      if (request === historyRequest.current) {
        setHistory(undefined);
        setHistoryError(requestError instanceof Error ? requestError.message : "Could not load hand history");
      }
    } finally {
      if (request === historyRequest.current) setHistoryLoading(false);
    }
  }

  useEffect(() => { loadOpponents(); }, []);
  useEffect(() => () => adviceRequest.current?.abort(), []);

  useEffect(() => {
    if (reviewMode) return; // a reviewed hand's blinds and stacks are not the live table's
    const next: Prefs = { blinds, stacks, opponent, exploit, players, autoContinue, autoSave, carryStacks, showDetails };
    try { window.localStorage.setItem(PREFS_KEY, JSON.stringify(next)); } catch { /* storage is optional */ }
  }, [blinds, stacks, opponent, exploit, players, autoContinue, autoSave, carryStacks, showDetails, reviewMode]);

  function beginAdviceRequest() {
    adviceRequest.current?.abort();
    const request = new AbortController();
    adviceRequest.current = request;
    setQuick(undefined);
    setLoading(true);
    return request;
  }

  function cancelAdviceRequest() {
    prefetch.cancel();
    if (!adviceRequest.current) return;
    adviceRequest.current.abort();
    adviceRequest.current = undefined;
    setQuick(undefined);
    setLoading(false);
  }

  function finishAdviceRequest(request: AbortController) {
    if (adviceRequest.current !== request || request.signal.aborted) return;
    adviceRequest.current = undefined;
    request.abort();
    setQuick(undefined);
    setLoading(false);
  }

  function changeOpponent(name: string) {
    if (name.trim() !== selectedOpponent.current) {
      selectedOpponent.current = name.trim();
      ++profileRequest.current;
      ++historyRequest.current;
      setProfile(null);
      setHistory(undefined);
      setHistoryLoading(false);
      setHistoryError("");
      cancelAdviceRequest();
    }
    setOpponent(name);
  }

  function adviceBody(nextActions: SpotAction[], nextBoard: string[], hero = heroCards) {
    return JSON.stringify({ ...spot, hero_cards: hero, actions: nextActions, board: nextBoard, opponent: opponent.trim() || null, exploit });
  }

  async function evaluate(nextActions = actions, nextBoard = board, options: { hero?: string[]; remember?: boolean } = {}) {
    setError(""); setNotice("");
    const payload = adviceBody(nextActions, nextBoard, options.hero);
    prefetch.commit(payload);
    const request = beginAdviceRequest();
    const input = {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: payload,
      signal: request.signal,
    };
    try {
      const body = await requestCoachAdvice(input, nextBoard.length >= 3 ? (preview) => {
        if (adviceRequest.current === request) setQuick({ ...preview, actions: nextActions });
      } : undefined);
      if (request.signal.aborted) return;
      if (options.remember && result) setPast((current) => [...current, { actions, board }]);
      setActions(nextActions); setBoard(nextBoard); setBoardDraft([]); setResult(body);
      setAmount(defaultAmount(body)); setTyped(false);
    } catch (requestError) {
      if (!request.signal.aborted) setError(requestError instanceof Error ? requestError.message : "Coach request failed");
    } finally {
      if (adviceRequest.current === request) prefetch.cancel();
      finishAdviceRequest(request);
    }
  }

  function beginHand(hero = heroCards) {
    setError(""); setBoardDraft([]); setVillainCards([]); setReviewMode(false); setLogged(false); setPast([]);
    loadProfile(opponent); loadHistory(opponent);
    blurFocus();
    evaluate([], [], { hero });
  }

  function start(event: FormEvent) {
    event.preventDefault();
    if (heroCards.length !== 2) { setError("Pick or type exactly two hero cards."); return; }
    beginHand();
  }

  function pickHeroCards(next: string[]) {
    cancelAdviceRequest();
    setHeroCards(next);
    if (autoContinue && next.length === 2 && heroCards.length < 2 && !loading) beginHand(next);
  }

  async function saveHand() {
    const response = await fetch("/api/coach/hands", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...spot, opponent: opponent.trim(), villain_cards: villainCards.length === 2 ? villainCards : null }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(describeError(body, "Could not log the hand"));
    if (opponent.trim() === selectedOpponent.current) {
      ++profileRequest.current;
      setProfile(body.opponent_profile);
      loadHistory(opponent);
    }
    loadOpponents();
    const count: number = body.opponent_profile.hands_observed;
    return `${opponent.trim()} now has ${count} ${count === 1 ? "hand" : "hands"} on record.`;
  }

  async function newHand() {
    if (loading) return;
    const finished = result?.status === "hand_complete" && !reviewMode ? result : null;
    let savedNote = "";
    let saveError = "";
    if (finished && autoSave && !logged && opponent.trim()) {
      setLoading(true);
      try { savedNote = `Saved last hand. ${await saveHand()}`; }
      catch (requestError) { saveError = `Last hand was not saved: ${requestError instanceof Error ? requestError.message : "unknown error"}`; }
      finally { setLoading(false); }
    }
    const net = finished?.summary.hero_net;
    if (finished && carryStacks && typeof net === "number") {
      const hero = +stacks.hero + net;
      const villain = +stacks.villain - net;
      if (hero > 0 && villain > 0) setStacks({ hero: String(hero), villain: String(villain) });
    }
    setHeroCards([]); setBoard([]); setBoardDraft([]); setVillainCards([]); setActions([]); setPast([]);
    setResult(undefined); setReviewMode(false); setLogged(false); setAmount(""); setTyped(false);
    setError(saveError); setNotice(savedNote);
    setPosition((current) => (current === "button" ? "big_blind" : "button"));
    setHandNumber((current) => current + 1);
    blurFocus();
  }

  function nextAction(actor: Actor, action: ActionKind, size?: number): SpotAction | undefined {
    const sized = action === "bet" || action === "raise";
    const total = size ?? Number(amount);
    if (sized && state) {
      const high = effectiveMaximum(state, actor);
      if ((size === undefined && !amount.trim()) || !Number.isInteger(total) || total < (state.minimum_target ?? 0) || total > high) {
        return;
      }
    }
    return { actor, action, amount: sized ? Math.round(total) : null };
  }

  function warmOpponentAction(actor: Actor, action: ActionKind, size?: number) {
    if (!loading && !reviewMode && actor === "villain" && result?.status === "villain_to_act" && board.length >= 3 && action !== "fold") {
      const candidate = nextAction(actor, action, size);
      if (candidate) prefetch.schedule(adviceBody([...actions, candidate], board));
      else prefetch.cancel();
    } else {
      prefetch.cancel();
    }
  }

  function act(actor: Actor, action: ActionKind, size?: number) {
    const candidate = nextAction(actor, action, size);
    if (!candidate && state) {
      setError(`Enter a whole-number total between ${state.minimum_target} and ${effectiveMaximum(state, actor)} to ${action}.`);
      return;
    }
    if (!candidate) return;
    blurFocus();
    evaluate([...actions, candidate], board, { remember: true });
  }

  function followAdvice() {
    if (result?.status !== "hero_to_act") return;
    act("hero", result.advice.action, result.advice.amount ?? undefined);
  }

  function undo() {
    if (loading || reviewMode) return;
    const previous = past[past.length - 1];
    if (previous) {
      setPast(past.slice(0, -1));
      evaluate(previous.actions, previous.board);
      return;
    }
    if (result) {
      // Nothing left to undo in this hand: go back to the cards so a mistyped card can be fixed.
      setResult(undefined); setActions([]); setBoard([]); setBoardDraft([]); setError(""); setNotice("");
    }
  }

  function submitBoard(cards: string[]) {
    if (result?.status !== "need_board") return;
    const needed = result.cards_needed - board.length;
    if (cards.length !== needed) {
      setError(`Enter exactly ${needed} card${needed > 1 ? "s" : ""}.`);
      return;
    }
    evaluate(actions, [...board, ...cards], { remember: true });
  }

  function addBoard(event: FormEvent) {
    event.preventDefault();
    submitBoard(boardDraft);
  }

  async function logHand() {
    if (!opponent.trim()) { setError("Enter the opponent's name to log this hand."); return; }
    setError(""); setLoading(true);
    try {
      setNotice(`Logged. ${await saveHand()}`);
      setLogged(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not log the hand");
    } finally {
      setLoading(false);
    }
  }

  async function viewHand(record: HandRecord) {
    setHistoryError("");
    const request = beginAdviceRequest();
    try {
      const response = await fetch("/api/coach/advise", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...record.spot, opponent: null, exploit: false }),
        signal: request.signal,
      });
      const body = await response.json();
      if (request.signal.aborted) return;
      if (!response.ok) throw new Error("Could not load this hand");
      setHeroCards(record.spot.hero_cards);
      setBoard(record.spot.board);
      setActions(record.spot.actions);
      setVillainCards(record.spot.villain_cards ?? []);
      setStacks({ hero: String(record.spot.hero_stack), villain: String(record.spot.villain_stack) });
      setBlinds({ small: String(record.spot.small_blind), big: String(record.spot.big_blind) });
      setPosition(record.spot.hero_position);
      setResult(body); setReviewMode(true); setLogged(false); setError(""); setNotice(""); setPast([]);
    } catch (requestError) {
      if (!request.signal.aborted) setHistoryError(requestError instanceof Error ? requestError.message : "Could not load this hand");
    } finally {
      finishAdviceRequest(request);
    }
  }

  async function deleteHand(id: number) {
    if (!window.confirm("Delete this hand? This cannot be undone.")) return;
    setDeletingId(id); setHistoryError("");
    try {
      const response = await fetch(`/api/coach/hands/${id}`, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Could not delete this hand");
      }
      setHistory((current) => current && { ...current, hands: current.hands.filter((record) => record.id !== id) });
      loadOpponents();
      const name = selectedOpponent.current;
      if (name) { loadProfile(name); loadHistory(name); }
    } catch (requestError) {
      setHistoryError(requestError instanceof Error ? requestError.message : "Could not delete this hand");
    } finally {
      setDeletingId(null);
    }
  }

  async function deleteOpponentHands() {
    const name = opponent.trim();
    if (!name) return;
    if (!window.confirm(`Delete all logged hands for ${name}? This cannot be undone.`)) return;
    setDeletingOpponent(true); setHistoryError("");
    try {
      const response = await fetch(`/api/coach/opponents/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Could not delete this opponent");
      }
      if (selectedOpponent.current === name) {
        setHistory(undefined); setProfile(null);
        loadHistory(name); loadProfile(name);
      }
      setNotice(`Deleted all hands for ${name}.`);
      loadOpponents();
    } catch (requestError) {
      setHistoryError(requestError instanceof Error ? requestError.message : "Could not delete this opponent");
    } finally {
      setDeletingOpponent(false);
    }
  }

  const state = result && "state" in result ? result.state : undefined;
  const displayedState = quick?.state ?? state;
  const displayedBoard = quick?.state.board ?? board;
  const displayedActions = quick?.actions ?? actions;
  const usedForHero = new Set([...board, ...boardDraft, ...villainCards]);
  const usedForBoard = new Set([...heroCards, ...villainCards, ...board]);
  const usedForVillain = new Set([...heroCards, ...board]);

  useLayoutEffect(() => {
    if (view === "play" && players === 1 && !reviewMode) {
      if (!autoContinue && result?.status === "need_board" && board.length + boardDraft.length === result.cards_needed) {
        prefetch.schedule(adviceBody(actions, [...board, ...boardDraft]));
      } else if (typed && result?.status === "villain_to_act") {
        const sized = result.state.legal_actions.find(action => action === "bet" || action === "raise");
        if (sized) warmOpponentAction("villain", sized);
      }
    }
    return () => prefetch.cancel();
  }, [prefetch, view, players, reviewMode, autoContinue, result, spot, boardDraft, opponent, exploit, amount, typed]);

  // Page-wide keyboard flow. Card typing lives in CardInput (capture phase), so a key it used arrives here already handled.
  useLayoutEffect(() => {
    if (view !== "play" || players > 1) return;
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target) || loading) return;
      const key = event.key;
      const onButton = (event.target as HTMLElement | null)?.tagName === "BUTTON";
      if (!result) {
        if (key === "Enter" && !onButton && heroCards.length === 2) { event.preventDefault(); beginHand(); }
        else if (key === "p" || key === "P") { event.preventDefault(); setPosition((current) => (current === "button" ? "big_blind" : "button")); }
        return;
      }
      if ((key === "n" || key === "N") && result.status === "hand_complete") { event.preventDefault(); newHand(); return; }
      if (key === "Backspace" || key === "z" || key === "Z") {
        if (key === "Backspace" && typed && amount) { event.preventDefault(); setAmount(amount.slice(0, -1)); return; }
        if (!reviewMode) { event.preventDefault(); undo(); }
        return;
      }
      if (result.status !== "hero_to_act" && result.status !== "villain_to_act") return;
      const actor: Actor = result.status === "hero_to_act" ? "hero" : "villain";
      const legal = result.state.legal_actions;
      const sizedAction = legal.find((candidate) => candidate === "bet" || candidate === "raise");
      if (/^[0-9]$/.test(key)) {
        if (!sizedAction) return;
        event.preventDefault();
        setAmount(typed ? amount + key : key); setTyped(true); setError("");
        return;
      }
      if (key === "Escape" && typed) { event.preventDefault(); setAmount(defaultAmount(result)); setTyped(false); return; }
      if (key === "Enter") {
        if (onButton) return;
        event.preventDefault();
        if (typed && sizedAction) act(actor, sizedAction);
        else if (actor === "hero") followAdvice();
        return;
      }
      const choice = ACTION_KEYS[key.toUpperCase()]?.find((candidate) => legal.includes(candidate));
      if (!choice) return;
      event.preventDefault();
      act(actor, choice);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function actionButtons(actor: Actor) {
    if (!state) return null;
    const sizedAction = state.legal_actions.find((a) => a === "bet" || a === "raise");
    const recent = actor === "villain" && sizedAction
      ? recentVillainSize(history, sizedAction, state, +blinds.big) : undefined;
    const advice = actor === "hero" && result?.status === "hero_to_act" ? result.advice : null;
    return (
      <div className="coach-actions">
        {advice && (
          <button type="button" className="primary coach-follow" disabled={loading} onClick={followAdvice}>
            I did this: {ACTION_TEXT[advice.action]}{advice.amount ? ` ${advice.amount}` : ""}{advice.action === "call" ? ` ${state.to_call}` : ""}
            <kbd aria-hidden="true">Enter</kbd>
          </button>
        )}
        <div className="coach-action-row">
        {state.legal_actions.map((action) => (
          <button key={action} type="button" className="secondary" disabled={loading} title={`Shortcut: ${KEY_FOR_ACTION[action]}`}
            onPointerEnter={() => warmOpponentAction(actor, action)} onFocus={() => warmOpponentAction(actor, action)}
            onClick={() => act(actor, action)}>
            {ACTION_TEXT[action]}{(action === "bet" || action === "raise") && amount ? ` ${amount}` : ""}{action === "call" ? ` ${state.to_call}` : ""}
            <span className="key-hint" aria-hidden="true">{KEY_FOR_ACTION[action]}</span>
          </button>
        ))}
        </div>
        {sizedAction && (
          <div className="coach-size-row">
            <label className="coach-amount">{actor === "hero" ? "Your" : "Their"} total this street
              <input
                inputMode="numeric" value={amount} className={typed ? "is-typed" : ""}
                onChange={(e) => { setAmount(e.target.value); setTyped(true); }}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  e.preventDefault();
                  if (!loading) act(actor, sizedAction);
                }}
              />
              <small>{state.minimum_target} – {effectiveMaximum(state, actor)}</small>
            </label>
            <div className="coach-quick-sizes" role="group" aria-label={`One click: ${ACTION_TEXT[sizedAction].toLowerCase()} this size`}>
              {recent !== undefined && (
                <button type="button" className="chip" disabled={loading} title="Most recent legal size from this opponent's logged hands"
                  onPointerEnter={() => warmOpponentAction(actor, sizedAction, recent)} onFocus={() => warmOpponentAction(actor, sizedAction, recent)}
                  onClick={() => act(actor, sizedAction, recent)}>
                  Recent <b>{recent}</b>
                </button>
              )}
              {quickSizes(state, actor).map((size) => (
                <button key={size.label} type="button" className="chip" disabled={loading} title={`${ACTION_TEXT[sizedAction]} ${size.amount}`}
                  onPointerEnter={() => warmOpponentAction(actor, sizedAction, size.amount)} onFocus={() => warmOpponentAction(actor, sizedAction, size.amount)}
                  onClick={() => act(actor, sizedAction, size.amount)}>
                  {size.label} <b>{size.amount}</b>
                </button>
              ))}
            </div>
          </div>
        )}
        <p className="kbd-help">
          {[
            actor === "hero" && <><kbd>Enter</kbd> I did what the Coach said</>,
            state.legal_actions.includes("fold") && <><kbd>F</kbd> fold</>,
            state.legal_actions.includes("call") ? <><kbd>C</kbd> call</> : state.legal_actions.includes("check") && <><kbd>C</kbd> check</>,
            sizedAction && <><kbd>B</kbd> {sizedAction}</>,
            state.legal_actions.includes("all_in") && <><kbd>A</kbd> all-in</>,
            sizedAction && <>type a number, then <kbd>Enter</kbd>, to {sizedAction} that total</>,
            <><kbd>Z</kbd> undo</>,
          ].filter(Boolean).map((item, index) => <span key={index}>{index > 0 && " · "}{item}</span>)}
        </p>
      </div>
    );
  }

  const opponentRow = (
    <div className="opponent-count" role="radiogroup" aria-label="Opponents in the hand">
      <span className="field-label">Opponents</span>
      <div className="segmented">
        {OPPONENT_COUNTS.map((count) => (
          <button
            key={count} type="button" role="radio" aria-checked={players === count}
            className={players === count ? "is-on" : ""}
            onClick={() => { if (count !== players) cancelAdviceRequest(); setPlayers(count); }} disabled={!!result && count !== players}
          >
            {count}
          </button>
        ))}
      </div>
      <small className="muted">{players === 1 ? "Heads-up: solver advice and opponent learning" : `${players}-way pot: equity and pot-odds advice`}</small>
    </div>
  );

  return (
    <section className="coach-panel">
      <div className="coach-head">
        <h2>Coach</h2>
        <div className="segmented" role="tablist" aria-label="Coach view">
          {([["play", "Play a hand"], ["review", "Review"], ["data", "Saved data"]] as const).map(([key, text]) => (
            <button key={key} type="button" role="tab" aria-selected={view === key} className={view === key ? "is-on" : ""} onClick={() => {
              if (view !== key) cancelAdviceRequest();
              setView(key);
              if (key !== "play") loadOpponents();
            }}>{text}</button>
          ))}
        </div>
      </div>

      {view === "review" ? <CoachReview opponents={opponents} /> : view === "data" ? <CoachData opponents={opponents} onChanged={() => { loadOpponents(); if (opponent.trim()) { loadProfile(opponent); loadHistory(opponent); } }} /> : (<>
      {opponentRow}
      {players > 1 ? <CoachMultiway key={players} opponents={players} /> : (<>
      {!result ? (
      <form onSubmit={start} className="coach-setup">
        <CardInput key={handNumber} label="Your cards" slots={["Card 1", "Card 2"]} cards={heroCards} onChange={pickHeroCards} usedCards={usedForHero} keyboard />
        <div className="setup-row">
          <div className="field">
            <span className="field-label" id="position-label">Your position <kbd className="kbd-inline">P</kbd></span>
            <div className="segmented" role="radiogroup" aria-labelledby="position-label">
              {([["button", "Button / SB"], ["big_blind", "Big blind"]] as const).map(([key, text]) => (
                <button key={key} type="button" role="radio" aria-checked={position === key} className={position === key ? "is-on" : ""} onClick={() => {
                  if (key !== position) cancelAdviceRequest();
                  setPosition(key);
                }}>{text}</button>
              ))}
            </div>
          </div>
          <label>Small blind<input inputMode="numeric" value={blinds.small} onChange={(e) => {
            cancelAdviceRequest(); setBlinds({ ...blinds, small: e.target.value });
          }} /></label>
          <label>Big blind<input inputMode="numeric" value={blinds.big} onChange={(e) => {
            cancelAdviceRequest(); setBlinds({ ...blinds, big: e.target.value });
          }} /></label>
          <label>Your stack<input inputMode="numeric" value={stacks.hero} onChange={(e) => {
            cancelAdviceRequest(); setStacks({ ...stacks, hero: e.target.value });
          }} /></label>
          <label>Their stack<input inputMode="numeric" value={stacks.villain} onChange={(e) => {
            cancelAdviceRequest(); setStacks({ ...stacks, villain: e.target.value });
          }} /></label>
        </div>
        <div className="setup-row">
          <label className="field-grow">Opponent name <span className="muted">(optional, so the Coach learns their style)</span><input list="coach-opponents" value={opponent} onChange={(e) => changeOpponent(e.target.value)} placeholder="e.g. Alex" />
            <datalist id="coach-opponents">{opponents.map((o) => <option key={o.name} value={o.name}>{o.hands} hands</option>)}</datalist>
          </label>
          <label className="coach-toggle"><input type="checkbox" checked={exploit} onChange={(e) => {
            cancelAdviceRequest(); setExploit(e.target.checked);
          }} />Adjust advice to this opponent</label>
        </div>
        <fieldset className="speed-options">
          <legend>Speed</legend>
          <label className="coach-toggle"><input type="checkbox" checked={autoContinue} onChange={(e) => setAutoContinue(e.target.checked)} />Go on as soon as the cards are in</label>
          <label className="coach-toggle"><input type="checkbox" checked={autoSave} onChange={(e) => setAutoSave(e.target.checked)} />Save each hand when I start the next</label>
          <label className="coach-toggle"><input type="checkbox" checked={carryStacks} onChange={(e) => setCarryStacks(e.target.checked)} />Carry stacks over to the next hand</label>
        </fieldset>
        <div className="coach-form-actions">
          <button className="primary" disabled={loading || heroCards.length !== 2}>{loading ? "Thinking…" : heroCards.length === 2 ? <>Start hand <kbd>Enter</kbd></> : `Pick ${2 - heroCards.length} more card${heroCards.length === 1 ? "" : "s"}`}</button>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
      ) : (
        <div className="hand-bar">
          <div className="hand-bar-cards">{heroCards.map((card) => <PlayingCard key={card} card={card} />)}</div>
          <span>{position === "button" ? "Button / SB" : "Big blind"} · {blinds.small}/{blinds.big} · stacks {stacks.hero} vs {stacks.villain}{opponent.trim() ? ` · vs ${opponent.trim()}` : ""}</span>
          {reviewMode && <span className="pill">Reviewing a logged hand</span>}
          <button type="button" className="secondary" onClick={newHand} disabled={loading}>New hand</button>
        </div>
      )}

      {notice && <p className="coach-notice" role="status">{notice}</p>}

      {result && (
        <div className="coach-layout">
          <div className="coach-main">
            <div className="coach-table">
              <div><span className="field-label">Board</span><div className="board-cards">{displayedBoard.length ? displayedBoard.map((c) => <PlayingCard key={c} card={c} />) : <span className="muted">Preflop</span>}</div></div>
              {displayedState && <div><span className="field-label">Pot</span><strong>{displayedState.pot}</strong>{displayedState.to_call > 0 && <span className="muted"> · to call {displayedState.to_call}</span>}</div>}
              {!quick && result.status === "need_board" && result.pot !== undefined && <div><span className="field-label">Pot</span><strong>{result.pot}</strong></div>}
            </div>

            {displayedActions.length > 0 && (
              <ol className="coach-log">
                {displayedActions.map((step, index) => <li key={index}>{describeAction(step)}</li>)}
              </ol>
            )}
            {!reviewMode && <button type="button" className="link-button" onClick={undo} disabled={loading}>{past.length > 0 ? "Undo last step" : "Back to my cards"} <kbd>Z</kbd></button>}

            {error && <p className="error" role="alert">{error}</p>}

            {quick && (
              <div className="coach-advice" role="status">
                <h3 className="coach-recommendation">Quick recommendation: {ACTION_TEXT[quick.advice.action]}</h3>
                <p className="coach-reason">{quick.reason} Full advice is calculating…</p>
              </div>
            )}

            {!quick && result.status === "villain_to_act" && (<div className="coach-step"><h3>{opponent.trim() || "Opponent"} to act</h3><p className="muted">What did they do?</p>{actionButtons("villain")}</div>)}

            {!quick && result.status === "need_board" && (() => {
              const needed = result.cards_needed - board.length;
              const slotName = result.street[0].toUpperCase() + result.street.slice(1);
              return (
                <form onSubmit={addBoard} className="coach-step">
                  <CardInput
                    key={`${result.street}-${board.length}`}
                    label={`Deal the ${result.street}`}
                    slots={Array(needed).fill(slotName)}
                    cards={boardDraft} usedCards={usedForBoard} keyboard={!loading}
                    onChange={(next) => {
                      setBoardDraft(next);
                      if (autoContinue && next.length === needed && boardDraft.length < needed && !loading) submitBoard(next);
                    }}
                  />
                  <button className="primary" disabled={loading || boardDraft.length !== needed}>{loading ? "Thinking…" : boardDraft.length === needed ? `Add ${result.street}` : `Pick ${needed - boardDraft.length} more`}</button>
                </form>
              );
            })()}

            {!quick && result.status === "hero_to_act" && (
              <div className="coach-advice">
                <h3 className="coach-recommendation">Recommended: {ACTION_TEXT[result.advice.action]}{result.advice.amount ? ` ${result.advice.amount}` : ""}</h3>
                {result.explain?.reason && <p className="coach-reason">{result.explain.reason}</p>}
                {actionButtons("hero")}
                <details className="coach-details" open={showDetails} onToggle={(e) => setShowDetails(e.currentTarget.open)}>
                <summary>Why: strategy mix, equity and their likely range</summary>
                {result.explain && <CoachStrategy options={result.explain.options} />}
                {result.explain?.ev_note && <p className="muted"><small>{result.explain.ev_note}</small></p>}
                {result.explanation.source !== "fallback" && (
                  <p className="muted">Mixed strategy from {result.explanation.source === "postflop_solve" ? "a real-time solve of this street" : result.explanation.source === "preflop_exploit" ? "the preflop chart re-solved for this opponent" : "the preflop chart"}.
                    {(result.adjusted ?? result.exploiting) ? " Adjusted to this opponent's tendencies." : ""}</p>
                )}
                {result.explanation.hero_equity_vs_range !== undefined && (
                  <p>Your equity vs their estimated range: <strong>{Math.round(result.explanation.hero_equity_vs_range * 100)}%</strong></p>
                )}
                {result.explanation.villain_range_makeup && (
                  <p className="coach-range"><small>THEIR ESTIMATED RANGE</small><br />{result.explanation.villain_range_makeup.filter((item) => item.share >= 0.01).map((item) => `${Math.round(item.share * 100)}% ${item.type}`).join(" · ")}</p>
                )}
                {result.explanation.villain_top_classes && (
                  <p className="coach-range"><small>MOST LIKELY VILLAIN HANDS</small><br />{result.explanation.villain_top_classes.slice(0, 10).map((item) => `${item.hand} ${Math.round(item.share * 100)}%`).join(" · ")}</p>
                )}
                </details>
              </div>
            )}

            {!quick && result.status === "hand_complete" && (
              <div className="coach-advice">
                <h3>Hand complete</h3>
                <p>{result.summary.showdown ? "Showdown." : foldedText(actions)} {result.summary.hero_net !== undefined && <strong className={result.summary.hero_net >= 0 ? "positive" : "negative"}>{result.summary.hero_net >= 0 ? "+" : ""}{result.summary.hero_net}</strong>}</p>
                {reviewMode ? (
                  <p className="muted">Loaded from hand history for review. Press <kbd>N</kbd> or "New hand" to enter a new one.</p>
                ) : (
                  <>
                    {result.summary.showdown && (
                      <CardInput label="Their shown cards (optional)" slots={["Card 1", "Card 2"]} cards={villainCards} onChange={setVillainCards} usedCards={usedForVillain} keyboard />
                    )}
                    <div className="coach-form-actions">
                      <button type="button" className="primary" onClick={newHand} disabled={loading}>Next hand <kbd>N</kbd></button>
                      {opponent.trim() && !autoSave && (
                        <button type="button" className="secondary" onClick={logHand} disabled={loading || logged}>{logged ? "Hand logged" : `Log hand vs ${opponent.trim()}`}</button>
                      )}
                    </div>
                    <p className="muted"><small>
                      {!opponent.trim() ? "Add an opponent name before the hand to save hands and learn their style."
                        : logged ? "This hand is saved."
                        : autoSave ? `Saved to ${opponent.trim()}'s profile when you start the next hand.`
                        : "Not saved unless you log it."}
                    </small></p>
                  </>
                )}
              </div>
            )}
          </div>

          <aside className="coach-profile">
            <div className="coach-panel-header">
              <h3>{opponent.trim() || "Opponent"}</h3>
              {opponent.trim() && (profile || history.length > 0) && (
                <button type="button" className="secondary danger" onClick={deleteOpponentHands} disabled={deletingOpponent}>
                  {deletingOpponent ? "Deleting..." : "Delete opponent"}
                </button>
              )}
            </div>
            {profile ? (
              <>
                <p><strong>{profile.classification.replace(/_/g, " ")}</strong> · {profile.hands_observed} {profile.hands_observed === 1 ? "hand" : "hands"}
                  {profile.label && <small className="muted"> · {profile.label.assigned ? `${profile.label.confidence.replace("_", " ")} confidence, based on ${profile.label.decisions} decisions` : "no label yet (needs 20+ hands)"}</small>}</p>
                <ul>
                  {Object.entries(profile.preflop).filter(([, read]) => read.opportunities > 0).map(([name, read]) => (
                    <li key={name}><span>{STAT_TEXT[name] ?? name}</span><b>{Math.round(read.frequency * 100)}%</b><small>{read.confidence.replace("_", " ")} ({read.opportunities})</small></li>
                  ))}
                  {POSTFLOP_STREETS.flatMap((street) => Object.entries(profile.postflop[street] ?? {})
                    .filter(([, read]) => read.opportunities > 0)
                    .map(([name, read]) => (
                      <li key={`${street}-${name}`}><span>{street[0].toUpperCase() + street.slice(1)}: {STAT_TEXT[name] ?? name}</span><b>{Math.round(read.frequency * 100)}%</b><small>{read.confidence.replace("_", " ")} ({read.opportunities})</small></li>
                    )))}
                </ul>
                <p className="muted">Reads need roughly 20+ opportunities before they carry weight.</p>
              </>
            ) : opponent.trim() ? <p className="muted">No logged hands yet. Log finished hands to build a profile.</p> : <p className="muted">Enter an opponent's name to track them.</p>}

            {opponent.trim() && (
              <div className="coach-history">
                <h4>Hand history</h4>
                {historyLoading && <p className="muted">Loading...</p>}
                {historyError && <p className="error" role="alert">{historyError}</p>}
                {!historyLoading && history.length === 0 && !historyError && <p className="muted">No hands logged yet.</p>}
                {history.length > 0 && (
                  <ul>
                    {history.map((record) => (
                      <li key={record.id}>
                        <button type="button" className="coach-history-entry" onClick={() => viewHand(record)} disabled={loading}>
                          <span className="coach-history-meta">
                            <span>{record.spot.hero_cards.join(" ")}{record.spot.board.length > 0 && ` · ${record.spot.board.join(" ")}`}</span>
                            <small>
                              {record.spot.actions.length > 0 && `${describeAction(record.spot.actions[record.spot.actions.length - 1])} · `}
                              {record.result?.hero_net != null && <><strong className={record.result.hero_net >= 0 ? "positive" : "negative"}>{record.result.hero_net >= 0 ? "+" : ""}{record.result.hero_net}</strong> · </>}
                              {new Date(record.created_at).toLocaleString()}
                            </small>
                          </span>
                        </button>
                        <button type="button" className="secondary danger" onClick={() => deleteHand(record.id)} disabled={deletingId === record.id}>
                          {deletingId === record.id ? "..." : "Delete"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </aside>
        </div>
      )}
      </>)}
      </>)}
    </section>
  );
}
