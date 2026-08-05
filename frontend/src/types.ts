export type Analysis = {
  street: string;
  hand_label: string;
  made_hand: string | null;
  draws: { type: string; outs_ranks: string[] }[];
  win_rate: number;
  tie_rate: number;
  loss_rate: number;
  equity: number;
  required_equity: number;
  final_pot_if_call: number;
  calculation_method: string;
  iterations: number;
  elapsed_ms: number;
  recommendation: string;
  explanation: string;
  disclaimer: string;
};

export type BotName = "random" | "tight" | "aggressive" | "equity";
export type MatchPlayer = "a" | "b";
export type MatchWinner = "Bot A" | "Bot B" | "tied";
export type MatchTerminationReason = "elimination" | "hand_limit";

export type MatchRequest = {
  bot_a: BotName;
  bot_b: BotName;
  starting_stack: number;
  small_blind: number;
  big_blind: number;
  max_hands: number;
  seed: number;
  equity_iterations: 500 | 1000 | 2000;
};

export type MatchHandSummary = {
  hand_number: number;
  button_player: MatchPlayer;
  small_blind_player: MatchPlayer;
  big_blind_player: MatchPlayer;
  starting_stack_a: number;
  starting_stack_b: number;
  ending_stack_a: number;
  ending_stack_b: number;
  winner: MatchWinner;
  net_chips_a: number;
  net_chips_b: number;
  showdown: boolean;
  fold_ended: boolean;
  board: string[];
  illegal_actions: number;
  fallback_diagnostics: Record<string, unknown>[];
  settlement_complete: boolean;
};

export type MatchResponse = {
  match_id: string;
  seed: number;
  bot_a: string;
  bot_b: string;
  starting_stack: number;
  small_blind: number;
  big_blind: number;
  max_hands: number;
  hands_played: number;
  final_stack_a: number;
  final_stack_b: number;
  winner: MatchWinner;
  termination_reason: MatchTerminationReason;
  bot_a_net_chips: number;
  bot_b_net_chips: number;
  showdowns: number;
  fold_ended_hands: number;
  illegal_actions: number;
  fallback_diagnostics: number;
  hand_summaries: MatchHandSummary[];
};

export type HistoryPlayer = "a" | "b";
export type HistoryWinner = HistoryPlayer | "tied";
export type HistoryEndingType = "fold" | "showdown";
export type HistoryStreet = "preflop" | "flop" | "turn" | "river" | string;
export type HistoryEventType =
  | "hand_started" | "blind_posted" | "action_taken" | "street_started"
  | "board_revealed" | "unmatched_excess_returned" | "automatic_runout_started"
  | "showdown" | "pot_awarded" | "hand_settled";
export type AllInClassification = "exact_call" | "short_call" | "short_raise" | "full_raise" | "non_raising_all_in" | "not_applicable" | string;
export type HistoryAction = string;

export type HandHistoryRequest = {
  bot_a: BotName; bot_b: BotName; starting_stack_a: number; starting_stack_b: number;
  small_blind: number; big_blind: number; button_player: HistoryPlayer; seed: number;
  equity_iterations: 500 | 1000 | 2000;
};
export type ValidationSummary = { valid: boolean; errors: string[]; warnings?: string[] };
export type HistoryEvent = {
  event_index: number; event_type: HistoryEventType; street: HistoryStreet; actor: HistoryPlayer | null;
  board: string[]; new_cards: string[]; pot_before: number; pot_after: number;
  stack_a_before: number; stack_a_after: number; stack_b_before: number; stack_b_after: number;
  street_commitment_a_before: number; street_commitment_a_after: number;
  street_commitment_b_before: number; street_commitment_b_after: number;
  current_highest_bet_before: number; current_highest_bet_after: number; settlement_complete: boolean;
  [key: string]: unknown;
};
export type HandHistory = {
  history_schema_version: string; hand_id: string; match_id: string | null; hand_number: number;
  hand_seed: number | null; simulation_seed: number | null; button_player: HistoryPlayer;
  small_blind_player: HistoryPlayer; big_blind_player: HistoryPlayer; small_blind_amount: number;
  big_blind_amount: number; starting_stack_a: number; starting_stack_b: number; events: HistoryEvent[];
  final_stack_a: number | null; final_stack_b: number | null; winner: HistoryWinner | null;
  ending_type: HistoryEndingType | null; final_board: string[]; showdown: boolean;
  settlement_complete: boolean; illegal_action_count: number; fallback_diagnostics: Record<string, unknown>[];
};
export type HandHistoryResponse = { document_type: "hand_history"; history_schema_version: string; history: HandHistory; validation: ValidationSummary };
