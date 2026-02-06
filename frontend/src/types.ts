// Message types matching Python models

export type MessageType =
  | 'sample_progress'
  | 'iteration_complete'
  | 'benchmark_status'
  | 'benchmark_complete'
  | 'error'
  | 'log';

export type BenchmarkMode = 'full_sweep' | 'quick';

export type BenchmarkState =
  | 'idle'
  | 'initializing'
  | 'stabilizing'
  | 'running'
  | 'paused'
  | 'stopping'
  | 'completed'
  | 'error';

export interface RefineRange {
  voltage_min: number;
  voltage_max: number;
  frequency_min: number;
  frequency_max: number;
}

export interface SampleData {
  hashrate: number;
  temperature: number;
  vr_temperature: number | null;
  power: number;
  input_voltage: number;
  fan_speed: number | null;
}

export interface SampleProgress {
  type: 'sample_progress';
  sample_number: number;
  total_samples: number;
  progress_percent: number;
  core_voltage: number;
  frequency: number;
  sample: SampleData;
  running_stddev: number;
  timestamp: string;
}

export interface IterationResult {
  core_voltage: number;
  frequency: number;
  average_hashrate: number;
  hashrate_stddev: number;
  average_temperature: number;
  average_vr_temperature: number | null;
  average_power: number;
  average_fan_speed: number | null;
  efficiency_jth: number;
  hashrate_within_tolerance: boolean;
  error_reason: string | null;
}

export interface IterationComplete {
  type: 'iteration_complete';
  result: IterationResult;
  iteration_number: number;
  next_voltage: number | null;
  next_frequency: number | null;
  timestamp: string;
}

export interface BenchmarkStatus {
  type: 'benchmark_status';
  state: BenchmarkState;
  current_voltage: number | null;
  current_frequency: number | null;
  iterations_completed: number;
  current_voltage_step: number | null;
  total_voltage_steps: number | null;
  message: string | null;
  timestamp: string;
}

export interface BenchmarkComplete {
  type: 'benchmark_complete';
  all_results: IterationResult[];
  best_hashrate: IterationResult | null;
  most_efficient: IterationResult | null;
  applied_settings: { voltage: number; frequency: number } | null;
  refine_range: RefineRange | null;
  total_duration_seconds: number;
  timestamp: string;
}

export interface ErrorMessage {
  type: 'error';
  error: string;
  details: string | null;
  timestamp: string;
}

export interface LogMessage {
  type: 'log';
  level: 'info' | 'warning' | 'error';
  message: string;
  timestamp: string;
}

export type WebSocketMessage =
  | SampleProgress
  | IterationComplete
  | BenchmarkStatus
  | BenchmarkComplete
  | ErrorMessage
  | LogMessage;

// Config types
export interface TimingConfig {
  sleep_time: number;
  benchmark_time: number;
  sample_interval: number;
}

export interface SafetyConfig {
  max_temp: number;
  max_vr_temp: number;
  max_power: number;
  max_allowed_voltage: number;
  min_allowed_voltage: number;
  max_allowed_frequency: number;
  min_allowed_frequency: number;
  min_input_voltage: number;
  max_input_voltage: number;
}

export interface IncrementsConfig {
  voltage_increment: number;
  frequency_increment: number;
}

export interface AnalysisConfig {
  hashrate_tolerance: number;
  trim_outliers: number;
  warmup_samples: number;
  min_samples: number;
}

export interface BenchmarkConfig {
  timing: TimingConfig;
  safety: SafetyConfig;
  increments: IncrementsConfig;
  analysis: AnalysisConfig;
}

// API types
export interface BenchmarkRequest {
  bitaxe_ip: string;
  initial_voltage?: number;
  initial_frequency?: number;
  max_temp?: number;
  mode?: BenchmarkMode;
  max_voltage?: number;
  max_frequency?: number;
}

export interface StatusResponse {
  state: BenchmarkState;
  is_running: boolean;
  is_paused: boolean;
  can_resume: boolean;
  iterations_completed: number;
  connections: number;
}
