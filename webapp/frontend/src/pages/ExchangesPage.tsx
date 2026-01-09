/**
 * Exchanges Page Component
 */
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { exchangesApi } from '@/services/api';
import DateRangeFilter from '@/components/DateRangeFilter';
import PlotlyChart from '@/components/PlotlyChart';

export default function ExchangesPage() {
  const [selectedCountry, setSelectedCountry] = useState('');
  const [dateRange, setDateRange] = useState<{ date_debut: string; date_fin: string } | null>(null);

  // Fetch metadata
  const { data: metadata } = useQuery({
    queryKey: ['exchanges-metadata'],
    queryFn: () => exchangesApi.getMetadata(),
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

      if (metadata.countries && metadata.countries.length > 0 && !selectedCountry) {
        setSelectedCountry(metadata.countries[0]);
      }
    }
  }, [metadata, dateRange, selectedCountry]);

  // Fetch chart data
  const { data: chartData, isLoading, error } = useQuery({
    queryKey: ['exchanges-chart', selectedCountry, dateRange],
    queryFn: async () => {
      if (!dateRange || !selectedCountry) return null;
      return exchangesApi.getCurve({ ...dateRange, pays: selectedCountry });
    },
    enabled: !!dateRange && !!selectedCountry,
  });

  const handleDateChange = (date_debut: string, date_fin: string) => {
    setDateRange({ date_debut, date_fin });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-navy-900">Échanges commerciaux</h1>
      </div>

      <DateRangeFilter
        onDateChange={handleDateChange}
        minDate={metadata?.available_dates.min_date}
        maxDate={metadata?.available_dates.max_date}
        defaultStartDate={dateRange?.date_debut}
        defaultEndDate={dateRange?.date_fin}
      />

      {/* Country Selector */}
      {metadata?.countries && (
        <div className="bg-white rounded-lg shadow p-6">
          <label htmlFor="country-select" className="block text-sm font-medium text-gray-700 mb-2">
            Pays
          </label>
          <select
            id="country-select"
            value={selectedCountry}
            onChange={(e) => setSelectedCountry(e.target.value)}
            className="w-full md:w-64 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-navy-500 focus:border-transparent"
          >
            {metadata.countries.map((country) => (
              <option key={country} value={country}>
                {country}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Chart */}
      <div className="bg-white rounded-lg shadow p-6">
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
  );
}
