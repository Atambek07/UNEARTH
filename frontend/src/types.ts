/** Контракты API UNEARTH — зеркало pydantic-схем backend/app/schemas.py. */

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

export interface FinanceResponse {
  capex_total_usd: number;
  capex_breakdown: CapexRow[];
  annual: FinanceAnnualRow[];
  chart: FinanceChartRow[];
  year0: { capex_usd: number; cumulative_cashflow_p50_usd: number };
  payback_years: number | null;
  irr: number | null;
  wacc: number;
  totals: {
    revenue_p50_usd: number;
    net_profit_p50_usd: number;
    co2_avoided_t: number;
    green_fund_usd: number;
    trees_planted: number;
    carbon_credit_upside_usd: number;
  };
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

export interface HealthResponse {
  status: string;
  prophet_available: boolean;
  version: string;
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

/* --------------------------- payload-типы ------------------------------ */

export interface ForecastPayload extends LandfillInputs {
  seed: number;
  use_prophet: boolean;
}

export interface OptimizePayload {
  available_mw: number;
  ch4_fraction: number;
  h2s_ppm: number;
  btc_price: number;
  gpu_rent_usd_per_gpu_hour: number;
  mode: AllocationMode;
  manual_miners: number;
  manual_ai_servers: number;
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
}

export interface SectorsPayload {
  ch4_m3_delivered_month: number;
  month: number;
  seed: number;
}
