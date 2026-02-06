import { useRef } from 'react';
import type { IterationResult } from '../types';

interface ResultsTableProps {
  results: IterationResult[];
  bestHashrateIndex?: number;
  mostEfficientIndex?: number;
  onExport?: () => Promise<void>;
  onImport?: (file: File) => Promise<void>;
}

export function ResultsTable({
  results,
  bestHashrateIndex,
  mostEfficientIndex,
  onExport,
  onImport,
}: ResultsTableProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onImport) {
      try {
        await onImport(file);
      } catch (err) {
        console.error('Import failed:', err);
      }
    }
    // Reset so the same file can be re-imported
    e.target.value = '';
  };

  if (results.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-white">Results</h2>
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileChange}
              className="hidden"
            />
            <button
              onClick={handleImportClick}
              className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
            >
              Import
            </button>
          </div>
        </div>
        <div className="text-gray-400 text-center py-8">
          No results yet. Start a benchmark or import previous results.
        </div>
      </div>
    );
  }

  // Find best and most efficient if not provided
  const bestIdx =
    bestHashrateIndex ??
    results.reduce(
      (best, r, i) =>
        r.average_hashrate > (results[best]?.average_hashrate ?? 0) ? i : best,
      0
    );
  const efficientIdx =
    mostEfficientIndex ??
    results.reduce(
      (best, r, i) =>
        r.efficiency_jth < (results[best]?.efficiency_jth ?? Infinity) ? i : best,
      0
    );

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-white">
          Results ({results.length} iterations)
        </h2>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            onClick={handleImportClick}
            className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
          >
            Import
          </button>
          {onExport && (
            <button
              onClick={onExport}
              className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
            >
              Export
            </button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-left border-b border-gray-700">
              <th className="pb-2 pr-4">#</th>
              <th className="pb-2 pr-4">Voltage</th>
              <th className="pb-2 pr-4">Frequency</th>
              <th className="pb-2 pr-4">Hashrate</th>
              <th className="pb-2 pr-4">Std Dev</th>
              <th className="pb-2 pr-4">Temp</th>
              <th className="pb-2 pr-4">Power</th>
              <th className="pb-2 pr-4">Efficiency</th>
              <th className="pb-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {results.map((result, index) => {
              const isBest = index === bestIdx;
              const isEfficient = index === efficientIdx;

              return (
                <tr
                  key={index}
                  className={`border-b border-gray-700/50 ${
                    isBest
                      ? 'bg-green-900/20'
                      : isEfficient
                      ? 'bg-blue-900/20'
                      : ''
                  }`}
                >
                  <td className="py-2 pr-4 text-gray-400">{index + 1}</td>
                  <td className="py-2 pr-4 font-mono text-white">
                    {result.core_voltage} mV
                  </td>
                  <td className="py-2 pr-4 font-mono text-white">
                    {result.frequency} MHz
                  </td>
                  <td className="py-2 pr-4 font-mono">
                    <span
                      className={
                        isBest ? 'text-green-400 font-bold' : 'text-white'
                      }
                    >
                      {result.average_hashrate.toFixed(1)}
                    </span>
                    <span className="text-gray-400 ml-1">GH/s</span>
                  </td>
                  <td className="py-2 pr-4 font-mono text-gray-300">
                    ±{result.hashrate_stddev.toFixed(1)}
                  </td>
                  <td className="py-2 pr-4 font-mono">
                    <span
                      className={
                        result.average_temperature > 60
                          ? 'text-red-400'
                          : 'text-white'
                      }
                    >
                      {result.average_temperature.toFixed(1)}°C
                    </span>
                  </td>
                  <td className="py-2 pr-4 font-mono text-white">
                    {result.average_power.toFixed(1)} W
                  </td>
                  <td className="py-2 pr-4 font-mono">
                    <span
                      className={
                        isEfficient ? 'text-blue-400 font-bold' : 'text-white'
                      }
                    >
                      {result.efficiency_jth.toFixed(2)}
                    </span>
                    <span className="text-gray-400 ml-1">J/TH</span>
                  </td>
                  <td className="py-2">
                    {result.error_reason ? (
                      <span className="text-red-400 text-xs">
                        {result.error_reason.replace(/_/g, ' ')}
                      </span>
                    ) : result.hashrate_within_tolerance ? (
                      <span className="text-green-400">✓ OK</span>
                    ) : (
                      <span className="text-yellow-400">⚠ Low</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="mt-4 flex gap-4 text-xs text-gray-400">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-green-900/50 rounded" />
          <span>Best Hashrate</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 bg-blue-900/50 rounded" />
          <span>Most Efficient</span>
        </div>
      </div>
    </div>
  );
}
