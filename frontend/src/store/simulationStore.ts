import { create } from 'zustand';
import { api } from '../api/client';
import type {
  AllocationMode,
  CarbonResponse,
  FiscalRegime,
  FinanceResponse,
  ForecastResponse,
  LandfillInputs,
  MaintenanceResponse,
  MarketCurrent,
  MarketInputs,
  MarketProvider,
  OptimizePathResponse,
  OptimizeResponse,
  ScenarioCompareResponse,
  ScenarioFull,
  ScenarioInputs,
  ScenarioListItem,
  SectorsResponse,
} from '../types';

/** Константы узлов — зеркало app/config.py backend'а. */
export const NODE_POWER_KW = { antminer: 3.25, aiServer: 1.5 } as const;
export const PUE_DC = 1.15;
export const DEFAULT_H2S_PPM = 30;
export const DEFAULT_MONTHS_OPERATED = 6;
export const N_SIMS = 400;
export const GPU_DEMAND_CAP = 1000;
export const PLAN_HORIZON_MONTHS = 12;

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

export type SliceKey =
  | 'market'
  | 'forecast'
  | 'optimize'
  | 'plan'
  | 'maintenance'
  | 'carbon'
  | 'finance'
  | 'sectors';
export type SliceStatus = 'idle' | 'loading' | 'done' | 'error';
export type SliceStatusMap = Record<SliceKey, SliceStatus>;
export type SliceErrorMap = Partial<Record<SliceKey, string>>;

export interface SimulationState {
  inputs: LandfillInputs;
  market: MarketInputs;
  marketProvider: MarketProvider;
  h2sPpm: number;
  mode: AllocationMode;
  manual: { miners: number; aiServers: number };
  monthsOperated: number;
  fiscalRegime: FiscalRegime;
  seed: number;

  apiOnline: boolean | null;
  marketQuote: MarketCurrent | null;
  forecast: ForecastResponse | null;
  optimize: OptimizeResponse | null;
  plan: OptimizePathResponse | null;
  maintenance: MaintenanceResponse | null;
  carbon: CarbonResponse | null;
  finance: FinanceResponse | null;
  sectors: SectorsResponse | null;

  scenarios: ScenarioListItem[];
  scenariosLoading: boolean;
  savingScenario: boolean;
  scenarioError: string | null;
  compare: ScenarioCompareResponse | null;
  selectedScenarioIds: number[];

  status: SliceStatusMap;
  errors: SliceErrorMap;
  running: boolean;
  lastRunAt: string | null;
  selectedSectorId: string | null;

  updateInputs: (patch: Partial<LandfillInputs>) => void;
  updateMarket: (patch: Partial<MarketInputs>) => void;
  setMarketProvider: (provider: MarketProvider) => void;
  setH2sPpm: (value: number) => void;
  setMode: (mode: AllocationMode) => void;
  setManual: (patch: Partial<{ miners: number; aiServers: number }>) => void;
  setMonthsOperated: (value: number) => void;
  setFiscalRegime: (regime: FiscalRegime) => void;
  setSelectedSector: (sectorId: string | null) => void;
  resetToBishkekDefaults: () => void;
  checkHealth: () => Promise<void>;
  run: () => Promise<void>;

  refreshScenarios: () => Promise<void>;
  saveScenario: (name: string) => Promise<boolean>;
  loadScenario: (id: number) => Promise<void>;
  deleteScenario: (id: number) => Promise<void>;
  toggleScenarioSelected: (id: number) => void;
  compareSelected: () => Promise<void>;
  clearCompare: () => void;
}

function initialStatus(): SliceStatusMap {
  return {
    market: 'idle',
    forecast: 'idle',
    optimize: 'idle',
    plan: 'idle',
    maintenance: 'idle',
    carbon: 'idle',
    finance: 'idle',
    sectors: 'idle',
  };
}

/** Ручное распределение: потребление парка с учётом PUE контейнеров, МВт. */
export function selectManualUsedMw(state: Pick<SimulationState, 'manual'>): number {
  return (
    (state.manual.miners * NODE_POWER_KW.antminer + state.manual.aiServers * NODE_POWER_KW.aiServer) *
    PUE_DC /
    1000
  );
}

/** Параметры сценария из текущего состояния (для сохранения в БД). */
export function selectScenarioInputs(state: SimulationState): ScenarioInputs {
  return {
    ...state.inputs,
    h2s_ppm: state.h2sPpm,
    mode: state.mode,
    manual_miners: state.manual.miners,
    manual_ai_servers: state.manual.aiServers,
    btc_price: state.market.btc_price,
    gpu_rent_usd_per_gpu_hour: state.market.gpu_rent_usd_per_gpu_hour,
    market_provider: state.marketProvider,
    seed: state.seed,
  };
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
    marketProvider: 'synthetic',
    h2sPpm: DEFAULT_H2S_PPM,
    mode: 'auto',
    manual: { miners: 0, aiServers: 0 },
    monthsOperated: DEFAULT_MONTHS_OPERATED,
    fiscalRegime: 'kr_htp',
    seed: 42,

    apiOnline: null,
    marketQuote: null,
    forecast: null,
    optimize: null,
    plan: null,
    maintenance: null,
    carbon: null,
    finance: null,
    sectors: null,

    scenarios: [],
    scenariosLoading: false,
    savingScenario: false,
    scenarioError: null,
    compare: null,
    selectedScenarioIds: [],

    status: initialStatus(),
    errors: {},
    running: false,
    lastRunAt: null,
    selectedSectorId: null,

    updateInputs: (patch) => set((state) => ({ inputs: { ...state.inputs, ...patch } })),
    updateMarket: (patch) => set((state) => ({ market: { ...state.market, ...patch } })),
    setMarketProvider: (provider) => set({ marketProvider: provider }),
    setH2sPpm: (value) => set({ h2sPpm: value }),
    setMode: (mode) => set({ mode }),
    setManual: (patch) => set((state) => ({ manual: { ...state.manual, ...patch } })),
    setMonthsOperated: (value) => set({ monthsOperated: value }),
    setFiscalRegime: (regime) => set({ fiscalRegime: regime }),
    setSelectedSector: (sectorId) => set({ selectedSectorId: sectorId }),
    resetToBishkekDefaults: () =>
      set({
        inputs: { ...DEFAULT_INPUTS },
        market: { ...DEFAULT_MARKET },
        marketProvider: 'synthetic',
        h2sPpm: DEFAULT_H2S_PPM,
        manual: { miners: 0, aiServers: 0 },
        monthsOperated: DEFAULT_MONTHS_OPERATED,
        fiscalRegime: 'kr_htp',
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
        compare: null,
      });

      /* Раунд 1: прогноз и рынок — независимы, идут параллельно. */
      await Promise.all([
        runSlice(
          'forecast',
          () =>
            api.forecast({
              ...snapshot.inputs,
              seed: snapshot.seed,
              use_prophet: false,
            }),
          (data) => ({ forecast: data }),
        ),
        runSlice(
          'market',
          () => api.market(snapshot.marketProvider, snapshot.seed),
          (data) => ({ marketQuote: data }),
        ),
      ]);

      const state = get();
      const forecast = state.forecast;
      if (!forecast) {
        set({ running: false });
        return;
      }

      /* В live-режиме цены берём с рынка; иначе — из боковой панели. */
      const live = state.marketProvider !== 'synthetic' && state.marketQuote?.source === 'live';
      const btcPayload = live ? null : state.market.btc_price;
      const rentPayload = live ? null : state.market.gpu_rent_usd_per_gpu_hour;
      const btcResolved = live ? (state.marketQuote?.btc_price_usd ?? state.market.btc_price) : state.market.btc_price;
      const rentResolved = live
        ? (state.marketQuote?.gpu_rent_usd_per_gpu_hour ?? state.market.gpu_rent_usd_per_gpu_hour)
        : state.market.gpu_rent_usd_per_gpu_hour;

      const availableMw = forecast.summary.year1_avg_power_mw;
      const firstMonth = forecast.monthly[0];
      const ch4DeliveredMonth = firstMonth.forecast_ch4_m3 * state.inputs.collection_efficiency;
      const planMonths = forecast.monthly.slice(0, PLAN_HORIZON_MONTHS);

      /* Раунд 2 (параллельно): балансировщик, план, сектора, обслуживание, карбон. */
      await Promise.all([
        runSlice(
          'optimize',
          () =>
            api.optimize({
              available_mw: availableMw,
              ch4_fraction: state.inputs.methane_fraction,
              h2s_ppm: state.h2sPpm,
              btc_price: btcPayload,
              gpu_rent_usd_per_gpu_hour: rentPayload,
              market_provider: state.marketProvider,
              mode: state.mode,
              manual_miners: state.manual.miners,
              manual_ai_servers: state.manual.aiServers,
              gpu_demand_cap: GPU_DEMAND_CAP,
              seed: state.seed,
            }),
          (data) => ({ optimize: data }),
        ),
        runSlice(
          'plan',
          () =>
            api.optimizePath({
              monthly_power_mw: planMonths.map((m) => m.avg_power_mw),
              monthly_moisture: planMonths.map((m) => m.moisture_index),
              ch4_fraction: state.inputs.methane_fraction,
              h2s_ppm: state.h2sPpm,
              btc_price: btcPayload,
              gpu_rent_usd_per_gpu_hour: rentPayload,
              market_provider: state.marketProvider,
              gpu_demand_cap: GPU_DEMAND_CAP,
              seed: state.seed,
            }),
          (data) => ({ plan: data }),
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
        runSlice(
          'carbon',
          () =>
            api.carbon({
              monthly_ch4_m3_delivered: forecast.monthly.map(
                (m) => m.forecast_ch4_m3 * state.inputs.collection_efficiency,
              ),
              gwp: 28,
              buffer_share: 0.2,
              verification_lag_months: 12,
              price_p10: 8,
              price_p50: 15,
              price_p90: 25,
              discount_rate: 0.1,
            }),
          (data) => ({ carbon: data }),
        ),
      ]);

      /* Раунд 3: финансы — нужны парк из балансировщика и OPEX из обслуживания. */
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
            btc_price: btcResolved,
            gpu_rent_usd_per_gpu_hour: rentResolved,
            opex_variable_annual_usd: maintenance?.opex_variable_annual_usd ?? 0,
            opex_fixed_annual_usd: maintenance?.opex_fixed_annual_usd ?? 0,
            seed: state.seed,
            n_sims: N_SIMS,
            fiscal_regime: state.fiscalRegime,
          }),
        (data) => ({ finance: data }),
      );

      set({ running: false, lastRunAt: new Date().toISOString() });
    },

    refreshScenarios: async () => {
      set({ scenariosLoading: true, scenarioError: null });
      try {
        const data = await api.scenarios.list();
        set({ scenarios: data.items, scenariosLoading: false });
      } catch (error) {
        set({
          scenariosLoading: false,
          scenarioError: error instanceof Error ? error.message : String(error),
        });
      }
    },

    saveScenario: async (name) => {
      const trimmed = name.trim();
      if (!trimmed) {
        set({ scenarioError: 'Укажите название сценария' });
        return false;
      }
      set({ savingScenario: true, scenarioError: null });
      try {
        await api.scenarios.create({
          name: trimmed,
          notes: '',
          inputs: selectScenarioInputs(get()),
          run: true,
        });
        const data = await api.scenarios.list();
        set({ scenarios: data.items, savingScenario: false });
        return true;
      } catch (error) {
        set({
          savingScenario: false,
          scenarioError: error instanceof Error ? error.message : String(error),
        });
        return false;
      }
    },

    loadScenario: async (id) => {
      set({ scenarioError: null });
      try {
        const scenario: ScenarioFull = await api.scenarios.get(id);
        const inp = scenario.inputs;
        const baseState = {
          inputs: {
            total_legacy_tonnes: inp.total_legacy_tonnes,
            annual_inflow_tonnes: inp.annual_inflow_tonnes,
            lo_m3_per_tonne: inp.lo_m3_per_tonne,
            k_per_year: inp.k_per_year,
            methane_fraction: inp.methane_fraction,
            horizon_years: inp.horizon_years,
            collection_efficiency: inp.collection_efficiency,
            genset_availability: inp.genset_availability,
            kwh_per_m3_ch4: inp.kwh_per_m3_ch4,
          },
          market: {
            btc_price: inp.btc_price ?? DEFAULT_MARKET.btc_price,
            gpu_rent_usd_per_gpu_hour:
              inp.gpu_rent_usd_per_gpu_hour ?? DEFAULT_MARKET.gpu_rent_usd_per_gpu_hour,
          },
          marketProvider: inp.market_provider,
          h2sPpm: inp.h2s_ppm,
          mode: inp.mode,
          manual: { miners: inp.manual_miners, aiServers: inp.manual_ai_servers },
        };

        /* Полный payload сохранён в БД — восстанавливаем без пересчёта модели. */
        const payload = scenario.results.payload;
        if (payload && payload.forecast && payload.optimize) {
          const status: SliceStatusMap = {
            market: 'idle',
            forecast: 'done',
            optimize: 'done',
            plan: payload.plan ? 'done' : 'idle',
            maintenance: payload.maintenance ? 'done' : 'idle',
            carbon: payload.carbon ? 'done' : 'idle',
            finance: payload.finance ? 'done' : 'idle',
            sectors: payload.sectors ? 'done' : 'idle',
          };
          set({
            ...baseState,
            forecast: payload.forecast,
            optimize: payload.optimize,
            plan: payload.plan ?? null,
            maintenance: payload.maintenance ?? null,
            carbon: payload.carbon ?? null,
            finance: payload.finance ?? null,
            sectors: payload.sectors ?? null,
            status,
            errors: {},
            running: false,
            selectedSectorId: null,
            lastRunAt: new Date().toISOString(),
          });
          return;
        }

        /* Старые сценарии без payload — пересчитываем по сохранённым входам. */
        set(baseState);
        await get().run();
      } catch (error) {
        set({ scenarioError: error instanceof Error ? error.message : String(error) });
      }
    },

    deleteScenario: async (id) => {
      set({ scenarioError: null });
      try {
        await api.scenarios.remove(id);
        set((state) => ({
          selectedScenarioIds: state.selectedScenarioIds.filter((item) => item !== id),
        }));
        const data = await api.scenarios.list();
        set({ scenarios: data.items });
      } catch (error) {
        set({ scenarioError: error instanceof Error ? error.message : String(error) });
      }
    },

    toggleScenarioSelected: (id) =>
      set((state) => {
        if (state.selectedScenarioIds.includes(id)) {
          return { selectedScenarioIds: state.selectedScenarioIds.filter((item) => item !== id) };
        }
        const next = [...state.selectedScenarioIds, id].slice(-4);
        return { selectedScenarioIds: next };
      }),

    compareSelected: async () => {
      const ids = get().selectedScenarioIds;
      if (ids.length < 2) {
        set({ scenarioError: 'Выберите минимум два сценария для сравнения' });
        return;
      }
      set({ scenarioError: null });
      try {
        const data = await api.scenarios.compare(ids);
        set({ compare: data });
      } catch (error) {
        set({ scenarioError: error instanceof Error ? error.message : String(error) });
      }
    },

    clearCompare: () => set({ compare: null, selectedScenarioIds: [] }),
  };
});
