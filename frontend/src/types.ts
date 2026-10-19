/** Контракты API UNEARTH v0.2 — зеркало backend/app/schemas.py и ответов routes.py. */

export interface ForecastMeta {
  model: string;
  prophet_used: boolean;
  history_months: number;
  ar1_rho: number;
  sigma_innov: number;
  seasonal_index: number[];
  seed: number;
  notes: string[];
}

export interface ForecastAnnualPoint {
  year: number;
  label: string;
  landgem_ch4_m3: number;
  forecast_ch4_m3: number;
  ci_lower: number;
  ci_upper: number;
  energy_mwh: number;
  avg_power_mw: number;
}

export interface ForecastMonthlyPoint {
  idx: number;
  label: string;
  year: number;
  month: number;
  landgem_ch4_m3: number;
  forecast_ch4_m3: number;
  ci_lower: number;
  ci_upper: number;
  moisture_index: number;
  energy_mwh: number;
  avg_power_mw: number;
}

export interface ForecastSummary {
  year1_avg_power_mw: number;
  year1_energy_mwh: number;
  year5_avg_power_mw: number;
  year_last_avg_power_mw: number;
  peak_power_mw: number;
  horizon_total_ch4_m3: number;
  horizon_total_energy_mwh: number;
}

export interface ForecastResponse {
  meta: ForecastMeta;
  annual: ForecastAnnualPoint[];
  monthly: ForecastMonthlyPoint[];
  summary: ForecastSummary;
}

export type MarketProvider = 'auto' | 'live' | 'synthetic';

export interface MarketCurrent {
  provider_requested: MarketProvider;
  source: 'live' | 'synthetic';
  btc_price_usd: number;
  network_hashrate_ths: number | null;
  network_hashrate_default_ths: number | null;
  gpu_rent_usd_per_gpu_hour: number;
  predicted_3m_return: number;
  miner_margin_multiplier: number;
  regime: MarketRegime;
  fetched_at: string | null;
  notes: string[];
  disclaimer: string;
}

export interface GasQuality {
  ch4_fraction: number;
  h2s_ppm: number;
  stability: number;
  h2s_penalty: number;
  derate_factor: number;
  stable: boolean;
}

export type MarketRegime = 'bearish' | 'neutral' | 'bullish';

export interface MarketState {
  btc_price: number;
  gpu_rent_usd_per_gpu_hour: number;
  predicted_3m_return: number;
  miner_margin_multiplier: number;
  regime: MarketRegime;
  source?: 'live' | 'synthetic';
  fetched_at?: string | null;
  network_hashrate_ths?: number | null;
  notes?: string[];
}

export type NodeType = 'antminer_s19_pro' | 'ai_server';

export interface AllocationRow {
  node_type: NodeType;
  label: string;
  count: number;
  unit_power_kw: number;
  power_mw: number;
  revenue_usd_day: number;
  margin_usd_day: number;
  margin_per_kw_day: number;
  status: 'running' | 'offline';
}

export interface OptimizeResponse {
  available_mw: number;
  allocatable_mw: number;
  quality: GasQuality;
  market: MarketState;
  margins: { mining_usd_per_kw_day: number; ai_usd_per_kw_day: number };
  allocation: AllocationRow[];
  used_mw: number;
  curtailed_mw: number;
  overcommitted: boolean;
  manual: boolean;
  shutdown_order: string[];
  rationale: string[];
}

/** Помесячный план упреждающего балансировщика (/api/optimize/path). */
export interface OptimizePathMonth {
  month: number;
  ai_servers: number;
  miners: number;
  used_mw: number;
  allocatable_mw: number;
  reserve_share: number;
  moisture_next: number;
  margin_usd_day: number;
  plan: 'greedy' | 'hold';
}

export interface OptimizePathSwitchEvent {
  month: number;
  added_miners: number;
  removed_miners: number;
  added_ai: number;
  removed_ai: number;
  cost_usd: number;
}

export interface OptimizePathResponse {
  months: number;
  quality: GasQuality;
  market: MarketState;
  margins: { mining_usd_per_kw_day: number; ai_usd_per_kw_day: number };
  plan: OptimizePathMonth[];
  switch_events: OptimizePathSwitchEvent[];
  switching_costs: { per_miner_usd: number; per_ai_usd: number; total_usd: number };
  totals: {
    optimized_margin_usd: number;
    optimized_switch_cost_usd: number;
    optimized_net_usd: number;
    naive_margin_usd: number;
    naive_switch_cost_usd: number;
    naive_net_usd: number;
    improvement_usd: number;
  };
  reserve_policy: { base_share: number; max_share: number; moisture_scale: number };
}

export interface GeneratorHealth {
  id: string;
  health_score: number;
  wear_pct_month: number;
  rul_months: number;
  failure_risk_12m: number;
  status: 'healthy' | 'degraded' | 'critical';
}

export interface MaintenanceResponse {
  installed_mw: number;
  genset_count: number;
  genset_rating_mw: number;
  wear_pct_month: number;
  gas: { lfg_flow_m3_month: number; h2s_ppm: number; sulfur_load_kg_month: number };
  generators: GeneratorHealth[];
  fleet_health_score: number;
  weakest: GeneratorHealth;
  scrubber: {
    beds: number;
    bed_capacity_kg: number;
    total_capacity_kg: number;
    load_kg_month: number;
    life_months: number;
    replacements_per_year: number;
    cost_per_replacement_usd: number;
    annual_cost_usd: number;
  };
  energy_mwh_month: number;
  opex_monthly_usd: {
    scrubbing_usd: number;
    consumables_usd: number;
    labor_usd: number;
    insurance_usd: number;
    plant_depreciation_usd: number;
    overhaul_reserve_usd: number;
    total_usd: number;
  };
  opex_variable_annual_usd: number;
  opex_fixed_annual_usd: number;
  opex_annual_usd: number;
}

export interface CapexRow {
  item: string;
  usd: number;
}

export interface FinanceAnnualRow {
  year: number;
  revenue_p10_usd: number;
  revenue_p50_usd: number;
  revenue_p90_usd: number;
  opex_usd: number;
  net_profit_p10_usd: number;
  net_profit_p50_usd: number;
  net_profit_p90_usd: number;
  cumulative_cashflow_p50_usd: number;
  co2_avoided_t: number;
  green_fund_usd: number;
  trees_planted: number;
}

export interface FinanceChartRow {
  label: string;
  capex_usd: number;
  opex_usd: number;
  net_profit_p50_usd: number;
  cumulative_cashflow_p50_usd: number;
}

export interface FiscalLine {
  item: string;
  base_usd: number;
  rate: number;
  amount_usd: number;
  note: string;
}

export interface FiscalYear {
  regime: string;
  lines: FiscalLine[];
  taxes_total_usd: number;
  net_profit_after_fiscal_usd: number;
  notes: string[];
  disclaimer: string;
}

export interface FiscalBlock {
  regime: FiscalRegime;
  years: FiscalYear[];
  totals: { taxes_total_usd: number; net_profit_after_fiscal_usd: number };
  disclaimer: string;
}

export interface CurrencyAnnualRow {
  year: number;
  gross_usd: number;
  conversion_cost_usd: number;
  repatriated_usd: number;
  repatriation_cost_usd: number;
  hedging_cost_usd: number;
  net_usd: number;
  kgs_received: number;
}

export interface CurrencyBlock {
  params: {
    usd_kgs_rate: number;
    conversion_spread: number;
    repatriation_share: number;
    repatriation_cost_share: number;
    hedging_cost_share: number;
  };
  annual: CurrencyAnnualRow[];
  totals: {
    gross_usd: number;
    conversion_cost_usd: number;
    repatriation_cost_usd: number;
    hedging_cost_usd: number;
    net_usd: number;
    kgs_received: number;
    cost_share: number;
  };
  notes: string[];
  disclaimer: string;
}

export interface FinanceResponse {
  capex_total_usd: number;
  capex_breakdown: CapexRow[];
  annual: FinanceAnnualRow[];
  chart: FinanceChartRow[];
  year0: { capex_usd: number; cumulative_cashflow_p50_usd: number };
  payback_years: number | null;
  irr: number | null;
  wacc: number;
  revenue_split: { ai_p50_usd: number[]; mining_p50_usd: number[] };
  totals: {
    revenue_p50_usd: number;
    net_profit_p50_usd: number;
    co2_avoided_t: number;
    green_fund_usd: number;
    trees_planted: number;
    carbon_credit_upside_usd: number;
  };
  fiscal?: FiscalBlock;
  fx?: CurrencyBlock;
}

/* ------------------------------ карбон --------------------------------- */

export interface CarbonAnnualRow {
  year: number;
  ch4_destroyed_m3: number;
  ch4_destroyed_t: number;
  baseline_co2e_t: number;
  buffer_credits_t: number;
  net_credits_t: number;
}

export interface CarbonScenario {
  price_usd_per_t: number;
  revenue_usd: number[];
  cashflow_usd: number[];
  npv_usd: number;
  total_revenue_usd: number;
  total_cash_usd: number;
}

export interface CarbonResponse {
  methodology: string;
  params: {
    gwp: number;
    buffer_share: number;
    verification_lag_months: number;
    discount_rate: number;
    issuance_fee_usd_per_credit: number;
    validation_cost_usd: number;
    verification_cost_usd_year: number;
    monitoring_cost_usd_year: number;
  };
  annual: CarbonAnnualRow[];
  totals: {
    ch4_destroyed_t: number;
    baseline_co2e_t: number;
    net_credits_t: number;
    buffer_credits_t: number;
  };
  scenarios: { p10: CarbonScenario; p50: CarbonScenario; p90: CarbonScenario };
  notes: string[];
  disclaimer: string;
}

export type SectorStatus = 'green' | 'amber' | 'red' | 'depleted';

export interface Sector {
  id: string;
  row: number;
  col: number;
  age_class: 'fresh' | 'mid' | 'old';
  ch4_flux_m3_h: number;
  h2s_ppm: number;
  instability_proba: number;
  status: SectorStatus;
  note: string;
}

export interface SectorsResponse {
  rows: number;
  cols: number;
  month: number;
  sectors: Sector[];
  summary: Record<SectorStatus, number>;
}

/* ------------------------------ сценарии -------------------------------- */

export interface ScenarioListItem {
  id: number;
  name: string;
  notes: string;
  created_at: string;
}

export interface ScenarioMetrics {
  year1_avg_power_mw?: number;
  peak_power_mw?: number;
  ai_servers?: number;
  miners?: number;
  used_mw?: number;
  daily_margin_usd?: number;
  fleet_health_score?: number;
  opex_annual_usd?: number;
  capex_total_usd?: number;
  payback_years?: number | null;
  irr?: number | null;
  net_profit_p50_usd?: number;
  co2_avoided_t?: number;
  green_fund_usd?: number;
  trees_planted?: number;
}

export interface ScenarioPayload {
  forecast?: ForecastResponse;
  optimize?: OptimizeResponse;
  plan?: OptimizePathResponse;
  maintenance?: MaintenanceResponse;
  carbon?: CarbonResponse;
  finance?: FinanceResponse;
  sectors?: SectorsResponse;
}

export interface ScenarioFull extends ScenarioListItem {
  inputs: ScenarioInputs;
  results: {
    digest?: ScenarioMetrics;
    generated_at?: string;
    payload_version?: number;
    payload?: ScenarioPayload;
  };
}

export interface ScenarioCompareResponse {
  comparison: Array<{
    id: number;
    name: string;
    created_at: string;
    metrics: ScenarioMetrics;
  }>;
  best: Record<string, number | null>;
  missing_ids: number[];
  disclaimer: string;
}

/* ------------------------------ входы ---------------------------------- */

export interface LandfillInputs {
  total_legacy_tonnes: number;
  annual_inflow_tonnes: number;
  lo_m3_per_tonne: number;
  k_per_year: number;
  methane_fraction: number;
  horizon_years: number;
  collection_efficiency: number;
  genset_availability: number;
  kwh_per_m3_ch4: number;
}

export interface MarketInputs {
  btc_price: number;
  gpu_rent_usd_per_gpu_hour: number;
}

export type AllocationMode = 'auto' | 'manual';
export type FiscalRegime = 'none' | 'kr_general' | 'kr_htp' | 'kz_aifc';

export interface ScenarioInputs extends LandfillInputs {
  h2s_ppm: number;
  mode: AllocationMode;
  manual_miners: number;
  manual_ai_servers: number;
  btc_price: number | null;
  gpu_rent_usd_per_gpu_hour: number | null;
  market_provider: MarketProvider;
  seed: number;
}

/* --------------------------- payload-типы ------------------------------ */

export interface ForecastPayload extends LandfillInputs {
  seed: number;
  use_prophet: boolean;
}

export interface OptimizePayload {
  available_mw: number;
  ch4_fraction: number;
  h2s_ppm: number;
  btc_price: number | null;
  gpu_rent_usd_per_gpu_hour: number | null;
  market_provider: MarketProvider;
  mode: AllocationMode;
  manual_miners: number;
  manual_ai_servers: number;
  gpu_demand_cap: number;
  seed: number;
}

export interface OptimizePathPayload {
  monthly_power_mw: number[];
  monthly_moisture: number[] | null;
  ch4_fraction: number;
  h2s_ppm: number;
  btc_price: number | null;
  gpu_rent_usd_per_gpu_hour: number | null;
  market_provider: MarketProvider;
  gpu_demand_cap: number;
  seed: number;
}

export interface MaintenancePayload {
  installed_mw: number;
  ch4_m3_month: number;
  h2s_ppm: number;
  methane_fraction: number;
  months_operated: number;
  genset_availability: number;
  kwh_per_m3_ch4: number;
}

export interface FinancePayload {
  horizon_years: number;
  monthly_power_mw: number[];
  monthly_ch4_m3_delivered: number[];
  miners_count: number;
  ai_servers_count: number;
  btc_price: number;
  gpu_rent_usd_per_gpu_hour: number;
  opex_variable_annual_usd: number;
  opex_fixed_annual_usd: number;
  seed: number;
  n_sims: number;
  fiscal_regime: FiscalRegime;
}

export interface CarbonPayload {
  monthly_ch4_m3_delivered: number[];
  gwp: number;
  buffer_share: number;
  verification_lag_months: number;
  price_p10: number;
  price_p50: number;
  price_p90: number;
  discount_rate: number;
}

export interface SectorsPayload {
  ch4_m3_delivered_month: number;
  month: number;
  seed: number;
}

export interface ScenarioCreatePayload {
  name: string;
  notes: string;
  inputs: ScenarioInputs;
  run: boolean;
}

export interface HealthResponse {
  status: string;
  prophet_available: boolean;
  version: string;
}
