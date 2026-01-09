/**
 * Plotly Chart Component
 */
import { useRef } from 'react';
import Plot from 'react-plotly.js';
import type { ChartData } from '@/types/api';

interface PlotlyChartProps {
  chartData: ChartData;
  className?: string;
}

export default function PlotlyChart({ chartData, className = '' }: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  if (!chartData || !chartData.data || chartData.data.length === 0) {
    return (
      <div className={`flex items-center justify-center h-96 bg-gray-50 rounded-lg ${className}`}>
        <p className="text-gray-500">Aucune donnée à afficher</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={className}>
      <Plot
        data={chartData.data as any}
        layout={{
          ...(chartData.layout as any),
          autosize: true,
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          font: {
            family: 'system-ui, -apple-system, sans-serif',
          },
        }}
        config={{
          ...chartData.config,
          responsive: true,
        }}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
}
