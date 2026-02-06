import type { SampleProgress } from '../types';

interface ProgressDisplayProps {
  progress: SampleProgress | null;
  voltageStep: { current: number; total: number } | null;
}

export function ProgressDisplay({ progress, voltageStep }: ProgressDisplayProps) {
  if (!progress) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <h2 className="text-lg font-semibold text-white mb-4">Live Progress</h2>
        <div className="text-gray-400 text-center py-8">
          Waiting for benchmark to start...
        </div>
      </div>
    );
  }

  const { sample, core_voltage, frequency, sample_number, total_samples, progress_percent, running_stddev } = progress;

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h2 className="text-lg font-semibold text-white mb-4">Live Progress</h2>

      {/* Voltage level indicator */}
      {voltageStep && (
        <div className="mb-3">
          <div className="flex justify-between text-sm text-gray-300 mb-1">
            <span className="font-medium text-orange-400">
              Voltage Level {voltageStep.current} of {voltageStep.total}
            </span>
            <span className="text-gray-400">
              {Math.round((voltageStep.current / voltageStep.total) * 100)}%
            </span>
          </div>
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-orange-500 transition-all duration-300"
              style={{ width: `${(voltageStep.current / voltageStep.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-gray-300 mb-1">
          <span>
            Sample {sample_number} / {total_samples}
          </span>
          <span>{progress_percent.toFixed(1)}%</span>
        </div>
        <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-300"
            style={{ width: `${progress_percent}%` }}
          />
        </div>
      </div>

      {/* Current settings */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-gray-700/50 rounded p-3">
          <div className="text-xs text-gray-400 uppercase">Core Voltage</div>
          <div className="text-xl font-mono text-white">{core_voltage} mV</div>
        </div>
        <div className="bg-gray-700/50 rounded p-3">
          <div className="text-xs text-gray-400 uppercase">Frequency</div>
          <div className="text-xl font-mono text-white">{frequency} MHz</div>
        </div>
      </div>

      {/* Live metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="Hashrate"
          value={sample.hashrate.toFixed(0)}
          unit="GH/s"
          color="text-green-400"
        />
        <MetricCard
          label="Std Dev"
          value={running_stddev.toFixed(0)}
          unit="GH/s"
          color="text-yellow-400"
        />
        <MetricCard
          label="Temperature"
          value={sample.temperature.toFixed(0)}
          unit="°C"
          color={sample.temperature > 60 ? 'text-red-400' : 'text-blue-400'}
        />
        <MetricCard
          label="Power"
          value={sample.power.toFixed(0)}
          unit="W"
          color="text-purple-400"
        />
        {sample.vr_temperature !== null && sample.vr_temperature > 0 && (
          <MetricCard
            label="VR Temp"
            value={sample.vr_temperature.toFixed(0)}
            unit="°C"
            color={sample.vr_temperature > 80 ? 'text-red-400' : 'text-orange-400'}
          />
        )}
        <MetricCard
          label="Input Voltage"
          value={sample.input_voltage.toFixed(0)}
          unit="mV"
          color="text-cyan-400"
        />
        {sample.fan_speed !== null && (
          <MetricCard
            label="Fan Speed"
            value={sample.fan_speed.toFixed(0)}
            unit="%"
            color="text-gray-300"
          />
        )}
      </div>
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value: string;
  unit: string;
  color?: string;
}

function MetricCard({ label, value, unit, color = 'text-white' }: MetricCardProps) {
  return (
    <div className="bg-gray-700/50 rounded p-2">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={`font-mono text-lg ${color}`}>
        {value}
        <span className="text-xs text-gray-400 ml-1">{unit}</span>
      </div>
    </div>
  );
}
