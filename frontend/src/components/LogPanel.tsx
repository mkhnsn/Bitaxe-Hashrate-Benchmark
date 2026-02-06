import { useRef, useEffect } from 'react';
import type { LogMessage } from '../types';

interface LogPanelProps {
  logs: LogMessage[];
}

export function LogPanel({ logs }: LogPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="bg-gray-800 rounded-lg p-4 flex flex-col min-h-[200px] max-h-[300px]">
      <h2 className="text-lg font-semibold text-white mb-4">Activity Log</h2>
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto font-mono text-sm bg-gray-900 rounded p-3"
      >
        {logs.length === 0 ? (
          <div className="text-gray-500">No activity yet...</div>
        ) : (
          logs.map((log, index) => (
            <div
              key={index}
              className={`py-0.5 ${
                log.level === 'error'
                  ? 'text-red-400'
                  : log.level === 'warning'
                  ? 'text-yellow-400'
                  : 'text-gray-300'
              }`}
            >
              <span className="text-gray-500 mr-2">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              {log.message}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
