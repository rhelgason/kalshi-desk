export type Employee = {
  key: string;
  name: string;
  title: string;
  emoji: string;
  blurb: string;
  status?: "active" | "suspended" | "fired";
  suspended_until?: string | null;
  level?: number;
  level_title?: string;
  multiplier?: number;
  strikes?: number;
  awards?: number;
  control?: boolean;
  autotune?: boolean;
  note?: string | null;
  practicing?: boolean; // not on this book: shown in the Live office, on the bench, practicing on Training
  overrides?: Record<string, unknown>;
  params?: Record<string, number | string | boolean | null | number[]>;
  backtestable?: boolean;
  starting_cash?: number;
  equity?: number;
  pnl?: number;
  roi?: number;
  realized_pnl?: number;
  open_positions?: number;
  fills?: number;
  wins?: number;
  losses?: number;
  win_rate?: number | null;
  fees?: number;
  max_drawdown?: number;
  brier?: number | null;
};

export type Position = {
  strategy: string;
  ticker: string;
  title: string;
  subtitle: string;
  yes: number;
  no: number;
  cost: number;
  mark: number | null;
  closes: string | null;
  strike?: number | null; // the market's target price
};

export type Underlying = {
  spot: number;
  implied_vol: number | null;
  realized_vol: number | null;
  momentum: Record<string, number>;
};

export type HRInfo = {
  award_name: string;
  review_days: number;
  last_review: string | null;
  next_review: string | null;
  reserve: number;
  levels: { title: string; multiplier: number; bet_pct?: number }[];
};

export type PoolSettings = {
  bet_pct: number;
  window_cap: number;
  daily_stop: number;
  brake_drawdown: number;
  brake_factor: number;
  max_bet?: number; // dollars, 0 = no cap
  timezone: string;
};

/** The office pool everyone but the control group bets out of (desk/paper/pool.py). */
export type PoolSummary = {
  equity: number;
  capital: number;
  pnl: number;
  cash: number;
  in_play: number;
  day_open: number;
  today: number;
  peak: number;
  stopped: boolean;
  stopped_at: string | null;
  braked: boolean;
  bet: number;
  window_cap: number;
  settings: PoolSettings;
  members: string[];
};

export type RosterRow = {
  key: string;
  status: "active" | "suspended" | "fired";
  suspended_until: string | null;
  level: number;
  strikes: number;
  params: Record<string, unknown>;
  autotune: boolean;
  control: boolean;
  awards: number;
  note: string | null;
  updated_at: string;
};

/** Money put in (+) or taken out (−) of the pool mid-season, pool-wide (desk/runner.py money_in_or_out) */
export type MoneyMove = { t: number; amount: number };

export type Policy = {
  season: number;
  hired?: string[]; // put on this book mid-season (desk/hr.py hire), over the yaml's `enabled: false`
  review_days: number;
  min_settled: number;
  promote_roi: number;
  demote_roi: number;
  demote_max_confidence: number;
  strikes_to_suspend: number;
  suspend_days: number;
  max_loss_suspend: number;
  auto_fire: boolean;
  strikes_to_fire: number;
  award_bonus: number;
  reserve: number;
  pool: PoolSettings;
  last_review: string | null;
  promote_min_confidence: number;
  realism: { depth: number; samples: number; measured_at: string | null; median_on_offer?: number };
  autotune: {
    enabled: boolean;
    every_hours: number;
    lookback_days: number;
    min_test_bets: number;
    min_improvement: number;
    min_confidence: number;
    requested_at: string | null;
    last_run: string | null;
  };
};

export type NewsItem = { id: number; ts: string; strategy: string | null; kind: string; detail: Record<string, any> };

export type TuningRun = {
  id: string;
  created_at: string;
  strategy: string;
  summary: {
    applied: boolean;
    why: string;
    changes: Record<string, unknown>;
    tried: number;
    current: { params: Record<string, unknown>; train: TuneResult; test: TuneResult };
    best: { params: Record<string, unknown>; train: TuneResult; test: TuneResult } | null;
    top: { params: Record<string, unknown>; train: TuneResult; test: TuneResult; holds_up: boolean }[];
  };
};

export type TuneResult = { pnl: number; bets: number; wins: number; roi: number; skill: number | null; realized_edge: number | null };

/** Paper or real money; for real money, the kill switch and the last check against Kalshi (desk/live). */
export type TradingStatus = {
  mode: "paper" | "live";
  env?: string;
  halted?: boolean;
  reason?: string;
  by?: string;
  at?: string;
  limits?: { max_order_dollars: number; max_order_pct?: number | null; max_orders_per_day: number; max_daily_loss: number; max_daily_loss_pct?: number | null; max_drift: number };
  books?: {
    at: string; ok: boolean;
    balance: number; // Kalshi's cash
    held?: number; // what Kalshi says the open positions are worth
    cash?: number; // Kalshi's cash as Kalshi reports it (balance also counts payouts on their way)
    expected: number; drift: number; baseline?: number;
    mismatches: Record<string, [number, number]>;
  } | null;
};

export type LiveStatus = {
  updated_at: string;
  started_at: string;
  tick_count: number;
  env: string;
  tick_seconds: number;
  season?: number;
  hr?: HRInfo;
  pool?: PoolSummary;
  trading?: TradingStatus;
  employees: Employee[];
  positions: Position[];
  underlyings: Record<string, Underlying>;
  crypto_events: string[];
};

export type CalibrationBin = { lo: number; hi: number; n: number; avg_forecast: number; hit_rate: number };

export type Accuracy = {
  strategy: string;
  n: number;
  hit_rate: number;
  avg_price: number;
  brier_market: number;
  brier_model: number | null;
  skill: number | null;
  expected_edge: number | null;
  realized_edge: number;
  model_bins: CalibrationBin[];
  market_bins: CalibrationBin[];
};

export type Fill = {
  id: number;
  ts: string;
  strategy: string;
  ticker: string;
  side: "yes" | "no";
  count: number;
  price: number;
  fee: number;
  model_prob: number | null;
  reason: string | null;
  yes_value: number | null;
  pnl: number | null;
};

export type Point = { t: number; v: number };
export type Series = { key: string; label: string; emoji: string; points: Point[] };

export type BacktestRow = {
  strategy: string;
  starting_cash: number;
  equity: number;
  pnl: number;
  roi: number;
  realized_pnl: number;
  fills: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  fees: number;
  max_drawdown: number;
  brier: number | null;
};

export type BacktestSummary = {
  id: string;
  days: number;
  series: string[];
  fill_delay: number;
  depth: number;
  settled_markets: number;
  stats: { minutes: number; intents: number; fills: number; skipped: number };
  scoreboard: BacktestRow[];
  accuracy: Accuracy[];
  equity?: Record<string, [string, number][]>;
  employees?: { key: string; name: string; emoji: string }[];
};

export type Evidence = {
  strategy: string;
  bets: number;
  contracts: number;
  edge: number;
  sd: number;
  pnl: number;
  pnl_1c: number;
  pnl_2c: number;
  confidence: number;
  confidence_1c: number;
  bets_needed: number | null;
  verdict: string;
  verdict_key: "too_early" | "strong" | "fragile" | "promising" | "losing" | "probably_not" | "luck";
};

export type Realism = {
  strategy: string;
  taker_fills: number;
  maker_fills: number;
  slippage: number | null;
  depth_share: number | null;
  median_depth: number | null;
  latency_s: number | null;
  verdict: string;
  verdict_key: "none" | "maker" | "too_big" | "slippy" | "realistic";
};
