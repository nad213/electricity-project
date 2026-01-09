/**
 * Consumption Page Component
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { consumptionApi } from '@/services/api';
import DateRangeFilter from '@/components/DateRangeFilter';
import PlotlyChart from '@/components/PlotlyChart';

type ViewMode = 'power' | 'annual' | 'monthly';

export default function ConsumptionPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('power');
  const [dateRange, setDateRange] = useState<{ date_debut: string; date_fin: string } | null>(null);

  // Fetch metadata
  const { data: metadata } = useQuery({
    queryKey: ['consumption-metadata'],
    queryFn: () => consumptionApi.getMetadata(),
  });

  // Set default date range when metadata is loaded
  useEffect(() => {
    if (metadata && !dateRange) {
      const today = new Date();
      const lastMonth = new Date(today);
      lastMonth.setMonth(today.getMonth() - 1);

      setDateRange({
        date_debut: lastMonth.toISOString().split('T')[0],
        date_fin: today.toISOString().split('T')[0],
      });
    }
  }, [metadata, dateRange]);

  // Fetch chart data based on view mode
  const { data: chartData, isLoading, error } = useQuery({
    queryKey: ['consumption-chart', viewMode, dateRange],
    queryFn: async () => {
      if (!dateRange) return null;

      switch (viewMode) {
        case 'power':
          return consumptionApi.getPowerCurve(dateRange);
        case 'annual':
          return consumptionApi.getAnnualChart(dateRange);
        case 'monthly':
          return consumptionApi.getMonthlyChart(dateRange);
        default:
          return null;
      }
    },
    enabled: !!dateRange,
  });

  const handleDateChange = (date_debut: string, date_fin: string) => {
    setDateRange({ date_debut, date_fin });
  };

  const handleExport = () => {
    if (!dateRange) return;

    let url = '';
    switch (viewMode) {
      case 'power':
        url = consumptionApi.exportPowerCSV(dateRange);
        break;
      case 'annual':
        url = consumptionApi.exportAnnualCSV(dateRange);
        break;
      case 'monthly':
        url = consumptionApi.exportMonthlyCSV(dateRange);
        break;
    }

    if (url) {
      window.open(url, '_blank');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-navy-900">Consommation électrique</h1>
      </div>

      <DateRangeFilter
        onDateChange={handleDateChange}
        minDate={metadata?.min_date}
        maxDate={metadata?.max_date}
        defaultStartDate={dateRange?.date_debut}
        defaultEndDate={dateRange?.date_fin}
      />

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
              Courbe de puissance
            </button>
            <button
              onClick={() => setViewMode('annual')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                viewMode === 'annual'
                  ? 'border-navy-600 text-navy-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Données annuelles
            </button>
            <button
              onClick={() => setViewMode('monthly')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                viewMode === 'monthly'
                  ? 'border-navy-600 text-navy-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Données mensuelles
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
            <>
              <PlotlyChart chartData={chartData} className="h-96" />
              <div className="mt-4 flex justify-end">
                <button
                  onClick={handleExport}
                  className="px-4 py-2 bg-green-600 text-white font-medium rounded-md hover:bg-green-700 transition-colors"
                >
                  Exporter en CSV
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
