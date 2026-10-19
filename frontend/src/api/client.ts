import type {
  CarbonPayload,
  CarbonResponse,
  FinancePayload,
  FinanceResponse,
  ForecastPayload,
  ForecastResponse,
  HealthResponse,
  MaintenancePayload,
  MaintenanceResponse,
  MarketCurrent,
  MarketProvider,
  OptimizePathPayload,
  OptimizePathResponse,
  OptimizePayload,
  OptimizeResponse,
  ScenarioCompareResponse,
  ScenarioCreatePayload,
  ScenarioFull,
  ScenarioListItem,
  SectorsPayload,
  SectorsResponse,
} from '../types';

// В dev-режиме запросы идут на тот же origin и проксируются Vite на :8000.
// В прод-сборке укажите VITE_API_URL (например, https://api.unearth.example).
const BASE_URL = import.meta.env.VITE_API_URL ?? '';

async function request<T>(path: string, body?: unknown, method?: 'GET' | 'POST' | 'DELETE'): Promise<T> {
  const httpMethod = method ?? (body === undefined ? 'GET' : 'POST');
  const response = await fetch(`${BASE_URL}${path}`, {
    method: httpMethod,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === 'string') {
        detail = payload.detail;
      } else if (payload.detail !== undefined) {
        detail = JSON.stringify(payload.detail);
      }
    } catch {
      // тело не JSON — оставляем статус
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export const api = {
  health: (): Promise<HealthResponse> => request<HealthResponse>('/api/health'),

  market: (provider: MarketProvider, seed = 42): Promise<MarketCurrent> =>
    request<MarketCurrent>(`/api/market/current?provider=${provider}&seed=${seed}`),

  forecast: (payload: ForecastPayload): Promise<ForecastResponse> =>
    request<ForecastResponse>('/api/forecast', payload),

  optimize: (payload: OptimizePayload): Promise<OptimizeResponse> =>
    request<OptimizeResponse>('/api/optimize', payload),

  optimizePath: (payload: OptimizePathPayload): Promise<OptimizePathResponse> =>
    request<OptimizePathResponse>('/api/optimize/path', payload),

  maintenance: (payload: MaintenancePayload): Promise<MaintenanceResponse> =>
    request<MaintenanceResponse>('/api/maintenance', payload),

  finance: (payload: FinancePayload): Promise<FinanceResponse> =>
    request<FinanceResponse>('/api/finance', payload),

  carbon: (payload: CarbonPayload): Promise<CarbonResponse> =>
    request<CarbonResponse>('/api/carbon', payload),

  sectors: (payload: SectorsPayload): Promise<SectorsResponse> =>
    request<SectorsResponse>('/api/sectors', payload),

  scenarios: {
    list: (limit = 100): Promise<{ items: ScenarioListItem[]; count: number }> =>
      request<{ items: ScenarioListItem[]; count: number }>(`/api/scenarios?limit=${limit}`),

    create: (payload: ScenarioCreatePayload): Promise<{ id: number; name: string; created_at: string }> =>
      request<{ id: number; name: string; created_at: string }>('/api/scenarios', payload),

    get: (id: number): Promise<ScenarioFull> => request<ScenarioFull>(`/api/scenarios/${id}`),

    remove: (id: number): Promise<{ deleted: number }> =>
      request<{ deleted: number }>(`/api/scenarios/${id}`, undefined, 'DELETE'),

    compare: (ids: number[]): Promise<ScenarioCompareResponse> =>
      request<ScenarioCompareResponse>('/api/scenarios/compare', { ids }),
  },
};
