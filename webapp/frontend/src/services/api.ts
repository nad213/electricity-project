/**
 * API Service for ElecFlow
 */
import axios from 'axios';
import type {
  ChartData,
  ConsumptionMetadata,
  ProductionMetadata,
  ExchangesMetadata,
  DateRangeParams,
  SectorParams,
  CountryParams,
} from '@/types/api';

const API_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Consumption API
export const consumptionApi = {
  getMetadata: async (): Promise<ConsumptionMetadata> => {
    const response = await api.get<ConsumptionMetadata>('/consumption/metadata/');
    return response.data;
  },

  getPowerCurve: async (params: DateRangeParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/consumption/power-curve/', { params });
    return response.data;
  },

  getAnnualChart: async (params: DateRangeParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/consumption/annual/', { params });
    return response.data;
  },

  getMonthlyChart: async (params: DateRangeParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/consumption/monthly/', { params });
    return response.data;
  },

  exportPowerCSV: (params: DateRangeParams): string => {
    const queryString = new URLSearchParams(params as any).toString();
    return `${API_URL}/consumption/export/power/?${queryString}`;
  },

  exportAnnualCSV: (params: DateRangeParams): string => {
    const queryString = new URLSearchParams(params as any).toString();
    return `${API_URL}/consumption/export/annual/?${queryString}`;
  },

  exportMonthlyCSV: (params: DateRangeParams): string => {
    const queryString = new URLSearchParams(params as any).toString();
    return `${API_URL}/consumption/export/monthly/?${queryString}`;
  },
};

// Production API
export const productionApi = {
  getMetadata: async (): Promise<ProductionMetadata> => {
    const response = await api.get<ProductionMetadata>('/production/metadata/');
    return response.data;
  },

  getPowerCurve: async (params: SectorParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/production/power-curve/', { params });
    return response.data;
  },

  getAnnualChart: async (params: DateRangeParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/production/annual/', { params });
    return response.data;
  },

  getMonthlyChart: async (params: DateRangeParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/production/monthly/', { params });
    return response.data;
  },
};

// Exchanges API
export const exchangesApi = {
  getMetadata: async (): Promise<ExchangesMetadata> => {
    const response = await api.get<ExchangesMetadata>('/exchanges/metadata/');
    return response.data;
  },

  getCurve: async (params: CountryParams): Promise<ChartData> => {
    const response = await api.get<ChartData>('/exchanges/curve/', { params });
    return response.data;
  },
};

export default api;
