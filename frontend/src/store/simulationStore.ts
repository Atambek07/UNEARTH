import { create } from 'zustand';
import { api } from '../api/client';
import type {
  AllocationMode,
  FinanceResponse,
  ForecastResponse,
  LandfillInputs,
  MaintenanceResponse,
  MarketInputs,
  OptimizeResponse,
  SectorsResponse,
} from '../types';

/** Константы узлов — зеркало app/config.py backend'а. */
export const NODE_POWER_KW = { antminer: 3.25, aiServer: 1.5 } as const;
export const PUE_DC = 1.15;
export const DEFAULT_H2S_PPM = 30;
export const DEFAULT_MONTHS_OPERATED = 6;
export const N_SIMS = 400;

/** Дефолты Бишкека из проектного досье (ЕБРР/Мэрия/EPA). */
export const DEFAULT_INPUTS: LandfillInputs = {
  total_legacy_tonnes: 20_000_000,
  annual_inflow_tonnes: 375_000,
  lo_m3_per_tonne: 75,
  k_per_year: 0.03,
  methane_fraction: 0.52,
  horizon_years: 15,
  collection_efficiency: 0.75,
  genset_availability: 0.92,
  kwh_per_m3_ch4: 3.5,
};

export const DEFAULT_MARKET: MarketInputs = {
  btc_price: 65_000,
  gpu_rent_usd_per_gpu_hour: 2.0,
};

export type SliceKey = 'forecast' | 'optimize' | 'maintenance' | 'finance' | 'sectors';
export type SliceStatus = 'idle' | 'loading' | 'done' | 'error';

export type SliceStatusMap = Record<SliceKey, SliceStatus>;
export type SliceErrorMap = Partial<Record<SliceKey, string>>;

export interface SimulationState {
  inputs: LandfillInputs;
  market: MarketInputs;
  h2sPpm: number;
  mode: AllocationMode;
  manual: { miners: number; aiServers: number };
  monthsOperated: number;
  seed: number;
  apiOnline: boolean | null;
  forecast: ForecastResponse | null;
  optimize: OptimizeResponse | null;
  maintenance: MaintenanceResponse | null;
  finance: FinanceResponse | null;
  sectors: SectorsResponse | null;
  status: SliceStatusMap;
  errors: SliceErrorMap;
  running: boolean;
  lastRunAt: string | null;
  selectedSectorId: string | null;

  updateInputs: (patch: Partial<LandfillInputs>) => void;
  updateMarket: (patch: Partial<MarketInputs>) => void;
  setH2sPpm: (value: number) => void;
  setMode: (mode: AllocationMode) => void;
  setManual: (patch: Partial<{ miners: number; aiServers: number }>) => void;
  setMonthsOperated: (value: number) => void;
  setSelectedSector: (sectorId: string | null) => void;
  resetToBishkekDefaults: () => void;
  checkHealth: () => Promise<void>;
  run: () => Promise<void>;
}

function initialStatus(): SliceStatusMap {
  return { forecast: 'idle', optimize: 'idle', maintenance: 'idle', finance: 'idle', sectors: 'idle' };
}

/** Ручное распределение: потребление парка с учётом PUE контейнеров, МВт. */
export function selectManualUsedMw(state: Pick<SimulationState, 'manual'>): number {
  return (
    (state.manual.miners * NODE_POWER_KW.antminer + state.manual.aiServers * NODE_POWER_KW.aiServer) *
    PUE_DC /
    1000
  );
}

export const useSimulation = create<SimulationState>()((set, get) => {
  const setSliceStatus = (key: SliceKey, status: SliceStatus, error?: string): void =>
    set((state) => ({
      status: { ...state.status, [key]: status },
      errors: { ...state.errors, [key]: error },
    }));

  /** Один асинхронный ML-запрос: статус loading → done/error + запись данных. */
  const runSlice = async <T>(
    key: SliceKey,
    request: () => Promise<T>,
    apply: (data: T) => Partial<SimulationState>,
  ): Promise<void> => {
    setSliceStatus(key, 'loading');
    try {
      const data = await request();
      set(apply(data));
      setSliceStatus(key, 'done');
    } catch (error) {
      setSliceStatus(key, 'error', error instanceof Error ? error.message : String(error));
    }
  };

  return {
    inputs: { ...DEFAULT_INPUTS },
    market: { ...DEFAULT_MARKET },
    h2sPpm: DEFAULT_H2S_PPM,
    mode: 'auto',
    manual: { miners: 0, aiServers: 0 },
    monthsOperated: DEFAULT_MONTHS_OPERATED,
    seed: 42,
    apiOnline: null,
    forecast: null,
    optimize: null,
    maintenance: null,
    finance: null,
    sectors: null,
    status: initialStatus(),
    errors: {},
    running: false,
    lastRunAt: null,
    selectedSectorId: null,

    updateInputs: (patch) => set((state) => ({ inputs: { ...state.inputs, ...patch } })),
    updateMarket: (patch) => set((state) => ({ market: { ...state.market, ...patch } })),
    setH2sPpm: (value) => set({ h2sPpm: value }),
    setMode: (mode) => set({ mode }),
    setManual: (patch) => set((state) => ({ manual: { ...state.manual, ...patch } })),
    setMonthsOperated: (value) => set({ monthsOperated: value }),
    setSelectedSector: (sectorId) => set({ selectedSectorId: sectorId }),
    resetToBishkekDefaults: () =>
      set({
        inputs: { ...DEFAULT_INPUTS },
        market: { ...DEFAULT_MARKET },
        h2sPpm: DEFAULT_H2S_PPM,
        manual: { miners: 0, aiServers: 0 },
        monthsOperated: DEFAULT_MONTHS_OPERATED,
      }),

    checkHealth: async () => {
      try {
        await api.health();
        set({ apiOnline: true });
      } catch {
        set({ apiOnline: false });
      }
    },

    run: async () => {
      const snapshot = get();
      set({
        running: true,
        selectedSectorId: null,
        status: initialStatus(),
        errors: {},
      });

      /* Раунд 1: прогноз — от него зависят все остальные модули. */
      await runSlice(
        'forecast',
        () =>
          api.forecast({
            ...snapshot.inputs,
            seed: snapshot.seed,
            use_prophet: false,
          }),
        (data) => ({ forecast: data }),
      );

      const state = get();
      const forecast = state.forecast;
      if (!forecast) {
        set({ running: false });
        return;
      }

      const availableMw = forecast.summary.year1_avg_power_mw;
      const firstMonth = forecast.monthly[0];
      const ch4DeliveredMonth = firstMonth.forecast_ch4_m3 * state.inputs.collection_efficiency;

      /* Раунд 2 (параллельно): балансировщик, сектора и обслуживание —
         все зависят только от прогноза. */
      await Promise.all([
        runSlice(
          'optimize',
          () =>
            api.optimize({
              available_mw: availableMw,
              ch4_fraction: state.inputs.methane_fraction,
              h2s_ppm: state.h2sPpm,
              btc_price: state.market.btc_price,
              gpu_rent_usd_per_gpu_hour: state.market.gpu_rent_usd_per_gpu_hour,
              mode: state.mode,
              manual_miners: state.manual.miners,
              manual_ai_servers: state.manual.aiServers,
              seed: state.seed,
            }),
          (data) => ({ optimize: data }),
        ),
        runSlice(
          'sectors',
          () =>
            api.sectors({
              ch4_m3_delivered_month: ch4DeliveredMonth,
              month: new Date().getMonth() + 1,
              seed: state.seed,
            }),
          (data) => ({ sectors: data }),
        ),
        runSlice(
          'maintenance',
          () =>
            api.maintenance({
              installed_mw: availableMw,
              ch4_m3_month: ch4DeliveredMonth,
              h2s_ppm: state.h2sPpm,
              methane_fraction: state.inputs.methane_fraction,
              months_operated: state.monthsOperated,
              genset_availability: state.inputs.genset_availability,
              kwh_per_m3_ch4: state.inputs.kwh_per_m3_ch4,
            }),
          (data) => ({ maintenance: data }),
        ),
      ]);

      /* Раунд 3: финансы — нужен парк из балансировщика и OPEX из обслуживания. */
      const optimize = get().optimize;
      const maintenance = get().maintenance;
      const miners = optimize?.allocation.find((r) => r.node_type === 'antminer_s19_pro')?.count ?? 0;
      const aiServers = optimize?.allocation.find((r) => r.node_type === 'ai_server')?.count ?? 0;

      await runSlice(
        'finance',
        () =>
          api.finance({
            horizon_years: state.inputs.horizon_years,
            monthly_power_mw: forecast.monthly.map((m) => m.avg_power_mw),
            monthly_ch4_m3_delivered: forecast.monthly.map(
              (m) => m.forecast_ch4_m3 * state.inputs.collection_efficiency,
            ),
            miners_count: miners,
            ai_servers_count: aiServers,
            btc_price: state.market.btc_price,
            gpu_rent_usd_per_gpu_hour: state.market.gpu_rent_usd_per_gpu_hour,
            opex_variable_annual_usd: maintenance?.opex_variable_annual_usd ?? 0,
            opex_fixed_annual_usd: maintenance?.opex_fixed_annual_usd ?? 0,
            seed: state.seed,
            n_sims: N_SIMS,
          }),
        (data) => ({ finance: data }),
      );

      set({ running: false, lastRunAt: new Date().toISOString() });
    },
  };
});
