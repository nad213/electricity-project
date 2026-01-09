/**
 * API Types for ElecFlow
 */

export interface PlotlyTrace {
  x: (string | number | Date)[];
  y: (string | number)[];
  type?: string;
  mode?: string;
  name?: string;
  line?: {
    width?: number;
  };
}

export interface PlotlyLayout {
  title?: string;
  xaxis?: {
    title?: string;
  };
  yaxis?: {
    title?: string;
  };
  hovermode?: string;
  barmode?: string;
}

export interface PlotlyConfig {
  displayModeBar?: boolean;
  displaylogo?: boolean;
}

export interface ChartData {
  data: PlotlyTrace[];
  layout: PlotlyLayout;
  config: PlotlyConfig;
}

export interface AvailableDates {
  min_date: string;
  max_date: string;
}

export interface ConsumptionMetadata {
  min_date: string;
  max_date: string;
}

export interface ProductionMetadata {
  sectors: string[];
  available_dates: {
    min_date: string;
    max_date: string;
  };
}

export interface ExchangesMetadata {
  countries: string[];
  available_dates: {
    min_date: string;
    max_date: string;
  };
}

export interface DateRangeParams {
  date_debut: string;
  date_fin: string;
}

export interface SectorParams extends DateRangeParams {
  secteur: string;
}

export interface CountryParams extends DateRangeParams {
  pays: string;
}

export interface APIError {
  error: string;
}
