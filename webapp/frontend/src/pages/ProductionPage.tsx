/**
 * Production Page Component
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { productionApi } from '@/services/api';
import DateRangeFilter from '@/components/DateRangeFilter';
import PlotlyChart from '@/components/PlotlyChart';

type ViewMode = 'power' | 'annual' | 'monthly';

export default function ProductionPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('power');
  const [selectedSector, setSelectedSector] = useState('');
  const [dateRange, setDateRange] = useState<{ date_debut: string; date_fin: string } | null>(null);

  // Fetch metadata
  const { data: metadata } = useQuery({
    queryKey: ['production-metadata'],
    queryFn: () => productionApi.getMetadata(),
  });

  // Set default values when metadata is loaded
  useEffect(() => {
    if (metadata && !dateRange) {
      const today = new Date();
      const lastMonth = new Date(today);
      lastMonth.setMonth(today.getMonth() - 1);

      setDateRange({
        date_debut: lastMonth.toISOString().split('T')[0],
        date_fin: today.toISOString().split('T')[0],
      });

      if (metadata.sectors && metadata.sectors.length > 0 && !selectedSector) {
        setSelectedSector(metadata.sectors[0]);
      }
    }
  }, [metadata, dateRange, selectedSector]);

  // Fetch chart data based on view mode
  const { data: chartData, isLoading, error } = useQuery({
    queryKey: ['production-chart', viewMode, selectedSector, dateRange],
    queryFn: async () => {
      if (!dateRange) return null;

      switch (viewMode) {
        case 'power':
          if (!selectedSector) return null;
          return productionApi.getPowerCurve({ ...dateRange, secteur: selectedSector });
        case 'annual':
          return productionApi.getAnnualChart(dateRange);
        case 'monthly':
          return productionApi.getMonthlyChart(dateRange);
        default:
          return null;
      }
    },
    enabled: !!dateRange && (viewMode !== 'power' || !!selectedSector),
  });

  const handleDateChange = (date_debut: string, date_fin: string) => {
    setDateRange({ date_debut, date_fin });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-navy-900">Production électrique</h1>
      </div>

      <DateRangeFilter
        onDateChange={handleDateChange}
        minDate={metadata?.available_dates.min_date}
        maxDate={metadata?.available_dates.max_date}
        defaultStartDate={dateRange?.date_debut}
        defaultEndDate={dateRange?.date_fin}
      />

      {/* Sector Selector (for power curve only) */}
      {viewMode === 'power' && metadata?.sectors && (
        <div className="bg-white rounded-lg shadow p-6">
          <label htmlFor="sector-select" className="block text-sm font-medium text-gray-700 mb-2">
            Filière énergétique
          </label>
          <select
            id="sector-select"
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="w-full md:w-64 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-navy-500 focus:border-transparent"
          >
            {metadata.sectors.map((sector) => (
              <option key={sector} value={sector}>
                {sector}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* View Mode Tabs */}
      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <nav className="flex -mb-px">
            <button
              onClick={() => setViewMode('power')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                viewMode === 'power'
                  ? 'border-navy-600 text-navy-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Courbe de production
            </button>
            <button
              onClick={() => setViewMode('annual')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                viewMode === 'annual'
                  ? 'border-navy-600 text-navy-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Production annuelle
            </button>
            <button
              onClick={() => setViewMode('monthly')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                viewMode === 'monthly'
                  ? 'border-navy-600 text-navy-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Production mensuelle
            </button>
          </nav>
        </div>

        <div className="p-6">
          {isLoading && (
            <div className="flex items-center justify-center h-96">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-navy-600 mx-auto"></div>
                <p className="mt-4 text-gray-600">Chargement des données...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">
                Erreur lors du chargement des données. Veuillez réessayer.
              </p>
            </div>
          )}

          {chartData && !isLoading && !error && (
            <PlotlyChart chartData={chartData} className="h-96" />
          )}
        </div>
      </div>
    </div>
  );
}
