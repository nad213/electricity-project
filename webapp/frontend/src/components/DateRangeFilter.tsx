/**
 * Date Range Filter Component
 */
import { useState, useEffect } from 'react';

interface DateRangeFilterProps {
  onDateChange: (startDate: string, endDate: string) => void;
  minDate?: string;
  maxDate?: string;
  defaultStartDate?: string;
  defaultEndDate?: string;
}

export default function DateRangeFilter({
  onDateChange,
  minDate,
  maxDate,
  defaultStartDate,
  defaultEndDate,
}: DateRangeFilterProps) {
  const [startDate, setStartDate] = useState(defaultStartDate || '');
  const [endDate, setEndDate] = useState(defaultEndDate || '');
  const [error, setError] = useState('');

  useEffect(() => {
    if (defaultStartDate) setStartDate(defaultStartDate);
    if (defaultEndDate) setEndDate(defaultEndDate);
  }, [defaultStartDate, defaultEndDate]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!startDate || !endDate) {
      setError('Veuillez sélectionner les deux dates');
      return;
    }

    if (new Date(startDate) > new Date(endDate)) {
      setError('La date de début doit être antérieure à la date de fin');
      return;
    }

    onDateChange(startDate, endDate);
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label htmlFor="start-date" className="block text-sm font-medium text-gray-700 mb-2">
            Date de début
          </label>
          <input
            type="date"
            id="start-date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            min={minDate}
            max={maxDate}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-navy-500 focus:border-transparent"
          />
        </div>

        <div>
          <label htmlFor="end-date" className="block text-sm font-medium text-gray-700 mb-2">
            Date de fin
          </label>
          <input
            type="date"
            id="end-date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            min={minDate}
            max={maxDate}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-navy-500 focus:border-transparent"
          />
        </div>

        <div className="flex items-end">
          <button
            type="submit"
            className="w-full px-6 py-2 bg-navy-600 text-white font-medium rounded-md hover:bg-navy-700 focus:outline-none focus:ring-2 focus:ring-navy-500 focus:ring-offset-2 transition-colors"
          >
            Afficher
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}
    </form>
  );
}
