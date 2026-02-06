import { useState, useEffect } from 'react';
import type { BenchmarkConfig, BenchmarkMode, BenchmarkState } from '../types';

const STORAGE_KEY = 'bitaxe-benchmark-settings';
const MODE_STORAGE_KEY = 'bitaxe-benchmark-mode';

interface SavedSettings {
  ip: string;
  voltage: string;
  frequency: string;
}

function loadSavedSettings(): SavedSettings {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch {
    // Ignore parse errors
  }
  return { ip: '', voltage: '', frequency: '' };
}

function saveSettings(settings: SavedSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Ignore storage errors
  }
}

interface BenchmarkControlsProps {
  config: BenchmarkConfig;
  state: BenchmarkState;
  onStart: (ip: string, voltage?: number, frequency?: number, mode?: BenchmarkMode) => Promise<void>;
  onStop: () => Promise<void>;
  onPause: () => Promise<void>;
  onResume: () => Promise<void>;
  onReset: () => Promise<void>;
}

export function BenchmarkControls({
  config,
  state,
  onStart,
  onStop,
  onPause,
  onResume,
  onReset,
}: BenchmarkControlsProps) {
  const [ip, setIp] = useState('');
  const [voltage, setVoltage] = useState<string>('');
  const [frequency, setFrequency] = useState<string>('');
  const [mode, setMode] = useState<BenchmarkMode>(() => {
    try {
      const saved = localStorage.getItem(MODE_STORAGE_KEY);
      if (saved === 'quick' || saved === 'full_sweep') return saved;
    } catch { /* ignore */ }
    return 'full_sweep';
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Load saved settings on mount
  useEffect(() => {
    const saved = loadSavedSettings();
    setIp(saved.ip);
    setVoltage(saved.voltage);
    setFrequency(saved.frequency);
  }, []);

  // Save settings when they change
  useEffect(() => {
    saveSettings({ ip, voltage, frequency });
  }, [ip, voltage, frequency]);

  // Persist mode
  useEffect(() => {
    try { localStorage.setItem(MODE_STORAGE_KEY, mode); } catch { /* ignore */ }
  }, [mode]);

  const isIdle = state === 'idle';
  const isRunning = state === 'running' || state === 'stabilizing' || state === 'initializing';
  const isPaused = state === 'paused';
  const isCompleted = state === 'completed';
  const isError = state === 'error';
  const isStopping = state === 'stopping';

  const canStart = isIdle;
  const canPause = isRunning;
  const canResume = isPaused;
  const canStop = isRunning || isPaused;
  const canReset = isCompleted || isError;
  const inputsDisabled = !isIdle;

  const handleStart = async () => {
    if (!ip) {
      setError('Please enter a Bitaxe IP address');
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const v = voltage ? parseInt(voltage, 10) : undefined;
      const f = frequency ? parseInt(frequency, 10) : undefined;

      // Validate voltage
      if (v !== undefined) {
        if (v < config.safety.min_allowed_voltage) {
          throw new Error(
            `Voltage must be at least ${config.safety.min_allowed_voltage}mV`
          );
        }
        if (v > config.safety.max_allowed_voltage) {
          throw new Error(
            `Voltage cannot exceed ${config.safety.max_allowed_voltage}mV`
          );
        }
      }

      // Validate frequency
      if (f !== undefined) {
        if (f < config.safety.min_allowed_frequency) {
          throw new Error(
            `Frequency must be at least ${config.safety.min_allowed_frequency}MHz`
          );
        }
        if (f > config.safety.max_allowed_frequency) {
          throw new Error(
            `Frequency cannot exceed ${config.safety.max_allowed_frequency}MHz`
          );
        }
      }

      await onStart(ip, v, f, mode);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start benchmark');
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action: () => Promise<void>, errorMsg: string) => {
    setLoading(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h2 className="text-lg font-semibold text-white mb-4">Benchmark Control</h2>

      <div className="space-y-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            Bitaxe IP Address
          </label>
          <input
            type="text"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            placeholder="192.168.1.100"
            disabled={inputsDisabled}
            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white placeholder-gray-400 disabled:opacity-50"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Initial Voltage (mV)
            </label>
            <input
              type="number"
              value={voltage}
              onChange={(e) => setVoltage(e.target.value)}
              placeholder="1150"
              disabled={inputsDisabled}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white placeholder-gray-400 disabled:opacity-50"
            />
            <span className="text-xs text-gray-400">
              {config.safety.min_allowed_voltage} - {config.safety.max_allowed_voltage}
            </span>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Initial Frequency (MHz)
            </label>
            <input
              type="number"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
              placeholder="500"
              disabled={inputsDisabled}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white placeholder-gray-400 disabled:opacity-50"
            />
            <span className="text-xs text-gray-400">
              {config.safety.min_allowed_frequency} - {config.safety.max_allowed_frequency}
            </span>
          </div>
        </div>

        {/* Mode toggle */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Sweep Mode</label>
          <div className="flex rounded overflow-hidden border border-gray-600">
            <button
              type="button"
              onClick={() => setMode('full_sweep')}
              disabled={inputsDisabled}
              className={`flex-1 px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                mode === 'full_sweep'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              Full Sweep
            </button>
            <button
              type="button"
              onClick={() => setMode('quick')}
              disabled={inputsDisabled}
              className={`flex-1 px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                mode === 'quick'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              Quick (4x steps)
            </button>
          </div>
          <span className="text-xs text-gray-400">
            {mode === 'quick'
              ? 'Coarse sweep with 4x step sizes. Suggests a refine range on completion.'
              : 'Full resolution sweep across all voltage/frequency combinations.'}
          </span>
        </div>

        {error && (
          <div className="text-red-400 text-sm bg-red-900/20 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* Control buttons */}
        <div className="flex flex-wrap gap-2">
          {/* Start button - only when idle */}
          {canStart && (
            <button
              onClick={handleStart}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded font-medium transition-colors"
            >
              {loading ? 'Starting...' : 'Start Benchmark'}
            </button>
          )}

          {/* Pause button - when running */}
          {canPause && (
            <button
              onClick={() => handleAction(onPause, 'Failed to pause')}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-600 text-white rounded font-medium transition-colors"
            >
              Pause
            </button>
          )}

          {/* Resume button - when paused */}
          {canResume && (
            <button
              onClick={() => handleAction(onResume, 'Failed to resume')}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded font-medium transition-colors"
            >
              Resume
            </button>
          )}

          {/* Stop button - when running or paused */}
          {canStop && (
            <button
              onClick={() => handleAction(onStop, 'Failed to stop')}
              disabled={loading || isStopping}
              className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white rounded font-medium transition-colors"
            >
              {isStopping ? 'Stopping...' : 'Stop'}
            </button>
          )}

          {/* Reset button - when completed or error */}
          {canReset && (
            <button
              onClick={() => handleAction(onReset, 'Failed to reset')}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white rounded font-medium transition-colors"
            >
              New Benchmark
            </button>
          )}
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-2 text-sm">
          <div
            className={`w-2 h-2 rounded-full ${
              isRunning
                ? 'bg-green-500 animate-pulse'
                : isPaused
                ? 'bg-yellow-500'
                : isCompleted
                ? 'bg-blue-500'
                : isError
                ? 'bg-red-500'
                : 'bg-gray-500'
            }`}
          />
          <span className="text-gray-300 capitalize">
            {state === 'idle'
              ? 'Ready'
              : state === 'paused'
              ? 'Paused (will resume after current iteration)'
              : state.replace('_', ' ')}
          </span>
        </div>
      </div>
    </div>
  );
}
