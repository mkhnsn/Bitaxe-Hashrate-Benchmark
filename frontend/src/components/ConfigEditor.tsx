import { useState, useEffect } from 'react';
import type { BenchmarkConfig } from '../types';

const CONFIG_EXPANDED_KEY = 'bitaxe-config-expanded';

interface ConfigEditorProps {
  config: BenchmarkConfig;
  onSave: (config: BenchmarkConfig) => Promise<void>;
  disabled?: boolean;
}

export function ConfigEditor({ config, onSave, disabled }: ConfigEditorProps) {
  const [editedConfig, setEditedConfig] = useState<BenchmarkConfig>(config);
  const [isExpanded, setIsExpanded] = useState(() => {
    try {
      return localStorage.getItem(CONFIG_EXPANDED_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync editedConfig when config prop changes (e.g., after fetch from API)
  useEffect(() => {
    setEditedConfig(config);
  }, [config]);

  // Persist expanded state
  useEffect(() => {
    try {
      localStorage.setItem(CONFIG_EXPANDED_KEY, String(isExpanded));
    } catch {
      // Ignore storage errors
    }
  }, [isExpanded]);

  const handleChange = (
    section: keyof BenchmarkConfig,
    key: string,
    value: string
  ) => {
    const numValue = parseFloat(value);
    if (isNaN(numValue)) return;

    setEditedConfig((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: numValue,
      },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(editedConfig);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = JSON.stringify(config) !== JSON.stringify(editedConfig);

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex justify-between items-center text-left"
      >
        <h2 className="text-lg font-semibold text-white">Configuration</h2>
        <span className="text-gray-400">{isExpanded ? '▼' : '▶'}</span>
      </button>

      {isExpanded && (
        <div className="mt-4 space-y-6">
          {/* Timing */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">Timing</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-400">
                  Sleep Time (s)
                </label>
                <input
                  type="number"
                  value={editedConfig.timing.sleep_time}
                  onChange={(e) =>
                    handleChange('timing', 'sleep_time', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Benchmark Time (s)
                </label>
                <input
                  type="number"
                  value={editedConfig.timing.benchmark_time}
                  onChange={(e) =>
                    handleChange('timing', 'benchmark_time', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Sample Interval (s)
                </label>
                <input
                  type="number"
                  value={editedConfig.timing.sample_interval}
                  onChange={(e) =>
                    handleChange('timing', 'sample_interval', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
            </div>
          </div>

          {/* Safety */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">
              Safety Limits
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-400">
                  Max Temp (°C)
                </label>
                <input
                  type="number"
                  value={editedConfig.safety.max_temp}
                  onChange={(e) =>
                    handleChange('safety', 'max_temp', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Max VR Temp (°C)
                </label>
                <input
                  type="number"
                  value={editedConfig.safety.max_vr_temp}
                  onChange={(e) =>
                    handleChange('safety', 'max_vr_temp', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Max Power (W)
                </label>
                <input
                  type="number"
                  value={editedConfig.safety.max_power}
                  onChange={(e) =>
                    handleChange('safety', 'max_power', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Min Voltage (mV)
                </label>
                <input
                  type="number"
                  value={editedConfig.safety.min_allowed_voltage}
                  onChange={(e) =>
                    handleChange('safety', 'min_allowed_voltage', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Max Voltage (mV)
                </label>
                <input
                  type="number"
                  value={editedConfig.safety.max_allowed_voltage}
                  onChange={(e) =>
                    handleChange('safety', 'max_allowed_voltage', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Max Frequency (MHz)
                </label>
                <input
                  type="number"
                  value={editedConfig.safety.max_allowed_frequency}
                  onChange={(e) =>
                    handleChange(
                      'safety',
                      'max_allowed_frequency',
                      e.target.value
                    )
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
            </div>
          </div>

          {/* Increments */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">
              Increments
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-400">
                  Voltage Step (mV)
                </label>
                <input
                  type="number"
                  value={editedConfig.increments.voltage_increment}
                  onChange={(e) =>
                    handleChange('increments', 'voltage_increment', e.target.value)
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400">
                  Frequency Step (MHz)
                </label>
                <input
                  type="number"
                  value={editedConfig.increments.frequency_increment}
                  onChange={(e) =>
                    handleChange(
                      'increments',
                      'frequency_increment',
                      e.target.value
                    )
                  }
                  disabled={disabled}
                  className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm disabled:opacity-50"
                />
              </div>
            </div>
          </div>

          {error && (
            <div className="text-red-400 text-sm">{error}</div>
          )}

          <div className="flex justify-end">
            <button
              onClick={handleSave}
              disabled={disabled || saving || !hasChanges}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded text-sm font-medium transition-colors"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
