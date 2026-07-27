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
