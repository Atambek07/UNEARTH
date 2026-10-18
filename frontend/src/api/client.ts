import type {
  FinancePayload,
  FinanceResponse,
  ForecastPayload,
  ForecastResponse,
  HealthResponse,
  MaintenancePayload,
  MaintenanceResponse,
  OptimizePayload,
  OptimizeResponse,
  SectorsPayload,
  SectorsResponse,
} from '../types';

// В dev-режиме запросы идут на тот же origin и проксируются Vite на :8000.
// В прод-сборке укажите VITE_API_URL (например, https://api.unearth.example).
const BASE_URL = import.meta.env.VITE_API_URL ?? '';

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
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

  forecast: (payload: ForecastPayload): Promise<ForecastResponse> =>
    request<ForecastResponse>('/api/forecast', payload),

  optimize: (payload: OptimizePayload): Promise<OptimizeResponse> =>
    request<OptimizeResponse>('/api/optimize', payload),

  maintenance: (payload: MaintenancePayload): Promise<MaintenanceResponse> =>
    request<MaintenanceResponse>('/api/maintenance', payload),

  finance: (payload: FinancePayload): Promise<FinanceResponse> =>
    request<FinanceResponse>('/api/finance', payload),

  sectors: (payload: SectorsPayload): Promise<SectorsResponse> =>
    request<SectorsResponse>('/api/sectors', payload),
};
