import { useCallback, useEffect, useState } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { BenchmarkControls } from './components/BenchmarkControls';
import { ConfigEditor } from './components/ConfigEditor';
import { ProgressDisplay } from './components/ProgressDisplay';
import { ResultsTable } from './components/ResultsTable';
import { LogPanel } from './components/LogPanel';
import type {
  BenchmarkConfig,
  BenchmarkMode,
  BenchmarkState,
  IterationResult,
  LogMessage,
  RefineRange,
  SampleProgress,
  WebSocketMessage,
} from './types';

const DEFAULT_CONFIG: BenchmarkConfig = {
  timing: { sleep_time: 90, benchmark_time: 600, sample_interval: 15 },
  safety: {
    max_temp: 66,
    max_vr_temp: 86,
    max_power: 30,
    max_allowed_voltage: 1400,
    min_allowed_voltage: 1000,
    max_allowed_frequency: 1200,
    min_allowed_frequency: 400,
    min_input_voltage: 4800,
    max_input_voltage: 5500,
  },
  increments: { voltage_increment: 15, frequency_increment: 20 },
  analysis: {
    hashrate_tolerance: 0.94,
    trim_outliers: 3,
    warmup_samples: 6,
    min_samples: 7,
  },
};

function App() {
  const [config, setConfig] = useState<BenchmarkConfig>(DEFAULT_CONFIG);
  const [state, setState] = useState<BenchmarkState>('idle');
  const [currentProgress, setCurrentProgress] = useState<SampleProgress | null>(null);
  const [results, setResults] = useState<IterationResult[]>([]);
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [refineRange, setRefineRange] = useState<RefineRange | null>(null);
  const [voltageStep, setVoltageStep] = useState<{ current: number; total: number } | null>(null);

  // Handle WebSocket messages
  const handleMessage = useCallback((message: WebSocketMessage) => {
    switch (message.type) {
      case 'sample_progress':
        setCurrentProgress(message);
        break;
      case 'iteration_complete':
        setResults((prev) => [...prev, message.result]);
        setCurrentProgress(null);
        break;
      case 'benchmark_status':
        setState(message.state);
        if (message.current_voltage_step != null && message.total_voltage_steps != null) {
          setVoltageStep({ current: message.current_voltage_step, total: message.total_voltage_steps });
        }
        if (message.message) {
          setLogs((prev) => [
            ...prev.slice(-99),
            { type: 'log', level: 'info', message: message.message!, timestamp: message.timestamp },
          ]);
        }
        break;
      case 'benchmark_complete':
        setState('completed');
        if (message.all_results.length > 0) {
          setResults(message.all_results);
        }
        setRefineRange(message.refine_range ?? null);
        setVoltageStep(null);
        break;
      case 'error':
        setLogs((prev) => [
          ...prev.slice(-99),
          { type: 'log', level: 'error', message: message.error, timestamp: message.timestamp },
        ]);
        break;
      case 'log':
        setLogs((prev) => [...prev.slice(-99), message]);
        break;
    }
  }, []);

  const { isConnected, error: wsError } = useWebSocket({
    onMessage: handleMessage,
  });

  // Fetch initial config
  useEffect(() => {
    fetch('/api/config')
      .then((res) => res.json())
      .then((data) => setConfig(data))
      .catch(console.error);
  }, []);

  // Fetch initial status and restore results if benchmark is active/completed
  useEffect(() => {
    fetch('/api/benchmark/status')
      .then((res) => res.json())
      .then((data) => {
        setState(data.state);
        // If not idle, restore accumulated results from the backend
        if (data.state !== 'idle') {
          fetch('/api/results/export/current')
            .then((res) => res.ok ? res.json() : null)
            .then((data) => {
              if (data?.all_results?.length) {
                setResults(data.all_results);
              }
            })
            .catch(console.error);
        }
      })
      .catch(console.error);
  }, []);

  const handleSaveConfig = async (newConfig: BenchmarkConfig) => {
    const res = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newConfig),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to save config');
    }
    setConfig(newConfig);
  };

  const handleStart = async (
    ip: string,
    voltage?: number,
    frequency?: number,
    mode?: BenchmarkMode,
    maxVoltage?: number,
    maxFrequency?: number,
  ) => {
    setResults([]);
    setLogs([]);
    setCurrentProgress(null);
    setRefineRange(null);
    setVoltageStep(null);

    const res = await fetch('/api/benchmark/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bitaxe_ip: ip,
        initial_voltage: voltage,
        initial_frequency: frequency,
        mode: mode || 'full_sweep',
        max_voltage: maxVoltage,
        max_frequency: maxFrequency,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start benchmark');
    }
  };

  const handleStop = async () => {
    const res = await fetch('/api/benchmark/stop', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to stop benchmark');
    }
  };

  const handlePause = async () => {
    const res = await fetch('/api/benchmark/pause', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to pause benchmark');
    }
  };

  const handleResume = async () => {
    const res = await fetch('/api/benchmark/resume', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to resume benchmark');
    }
  };

  const handleReset = async () => {
    const res = await fetch('/api/benchmark/reset', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to reset benchmark');
    }
    setResults([]);
    setLogs([]);
    setCurrentProgress(null);
    setRefineRange(null);
    setVoltageStep(null);
  };

  const handleRefine = async () => {
    if (!refineRange) return;
    // Read the saved IP from localStorage
    let ip = '';
    try {
      const saved = localStorage.getItem('bitaxe-benchmark-settings');
      if (saved) ip = JSON.parse(saved).ip;
    } catch { /* ignore */ }
    if (!ip) return;

    // Reset first
    await handleReset();
    // Start a full_sweep within the refine range
    await handleStart(
      ip,
      refineRange.voltage_min,
      refineRange.frequency_min,
      'full_sweep',
      refineRange.voltage_max,
      refineRange.frequency_max,
    );
  };

  const handleExport = async () => {
    const res = await fetch('/api/results/export/current');
    if (!res.ok) {
      throw new Error('Failed to export results');
    }
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    a.download = `benchmark_results_${timestamp}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/results/import', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to import results');
    }
    const data = await res.json();
    setResults(data.results);
    setLogs((prev) => [
      ...prev.slice(-99),
      {
        type: 'log' as const,
        level: 'info' as const,
        message: `Imported ${data.iterations_completed} iterations${data.bitaxe_ip ? ` from ${data.bitaxe_ip}` : ''}`,
        timestamp: new Date().toISOString(),
      },
    ]);
  };

  const isRunning = state !== 'idle' && state !== 'completed' && state !== 'error';

  return (
    <div className="h-screen bg-gray-900 text-white flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold">
            <span className="text-orange-500">Bitaxe</span> Hashrate Benchmark
          </h1>
          <div className="flex items-center gap-3 text-sm">
            <div className="flex items-center gap-1.5">
              <div
                className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-green-500' : 'bg-red-500'
                }`}
              />
              <span className="text-gray-400">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {wsError && (
              <span className="text-red-400">{wsError}</span>
            )}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 overflow-hidden">
        <div className="h-full grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left column - Controls */}
          <div className="space-y-4 overflow-y-auto">
            <BenchmarkControls
              config={config}
              state={state}
              onStart={handleStart}
              onStop={handleStop}
              onPause={handlePause}
              onResume={handleResume}
              onReset={handleReset}
            />
            <ConfigEditor
              config={config}
              onSave={handleSaveConfig}
              disabled={isRunning}
            />
          </div>

          {/* Center column - Progress & Results */}
          <div className="lg:col-span-2 flex flex-col gap-4 min-h-0 overflow-y-auto">
            {/* Refine Search banner */}
            {refineRange && state === 'completed' && (
              <div className="bg-yellow-900/30 border border-yellow-600 rounded-lg p-4 flex items-center justify-between">
                <div>
                  <div className="text-yellow-400 font-medium">Quick Sweep Complete — Refine Available</div>
                  <div className="text-sm text-yellow-300/80 mt-1">
                    Best result found near {refineRange.voltage_min}-{refineRange.voltage_max}mV /{' '}
                    {refineRange.frequency_min}-{refineRange.frequency_max}MHz.
                    Run a full-resolution sweep in this range for optimal settings.
                  </div>
                </div>
                <button
                  onClick={handleRefine}
                  className="ml-4 shrink-0 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded font-medium transition-colors"
                >
                  Refine Search
                </button>
              </div>
            )}
            <ProgressDisplay progress={currentProgress} voltageStep={voltageStep} />
            <ResultsTable
              results={results}
              onExport={handleExport}
              onImport={handleImport}
            />
            <LogPanel logs={logs} />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-2 text-center text-gray-500 text-sm shrink-0">
        Bitaxe Hashrate Benchmark v2.0 | Use at your own risk
      </footer>
    </div>
  );
}

export default App;
