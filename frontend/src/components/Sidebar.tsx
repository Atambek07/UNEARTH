import type { ReactNode } from 'react';
import { Bot, Loader2, Play, RotateCcw, SlidersHorizontal } from 'lucide-react';
import { PUE_DC, selectManualUsedMw, useSimulation } from '../store/simulationStore';
import type { FiscalRegime, MarketProvider } from '../types';
import { fmtNum } from '../utils/format';

function Section({ title, children }: { title: string; children: ReactNode }): JSX.Element {
  return (
    <section className="space-y-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">{title}</h3>
      {children}
    </section>
  );
}

function NumberField({
  label,
  suffix,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string;
  suffix?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
}): JSX.Element {
  return (
    <label className="block">
      <span className="mb-1 flex items-center justify-between text-xs text-slate-400">
        <span>{label}</span>
        {suffix ? <span className="text-slate-500">{suffix}</span> : null}
      </span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 transition focus:border-emerald-500 focus:outline-none"
      />
    </label>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  format: (value: number) => string;
}): JSX.Element {
  return (
    <label className="block">
      <span className="mb-1 flex items-center justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="font-medium text-emerald-400">{format(value)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-emerald-500"
      />
    </label>
  );
}

export function Sidebar(): JSX.Element {
  const inputs = useSimulation((s) => s.inputs);
  const market = useSimulation((s) => s.market);
  const h2sPpm = useSimulation((s) => s.h2sPpm);
  const mode = useSimulation((s) => s.mode);
  const manual = useSimulation((s) => s.manual);
  const monthsOperated = useSimulation((s) => s.monthsOperated);
  const running = useSimulation((s) => s.running);
  const updateInputs = useSimulation((s) => s.updateInputs);
  const updateMarket = useSimulation((s) => s.updateMarket);
  const setH2sPpm = useSimulation((s) => s.setH2sPpm);
  const setMode = useSimulation((s) => s.setMode);
  const setManual = useSimulation((s) => s.setManual);
  const setMonthsOperated = useSimulation((s) => s.setMonthsOperated);
  const resetToBishkekDefaults = useSimulation((s) => s.resetToBishkekDefaults);
  const marketProvider = useSimulation((s) => s.marketProvider);
  const setMarketProvider = useSimulation((s) => s.setMarketProvider);
  const marketQuote = useSimulation((s) => s.marketQuote);
  const fiscalRegime = useSimulation((s) => s.fiscalRegime);
  const setFiscalRegime = useSimulation((s) => s.setFiscalRegime);
  const run = useSimulation((s) => s.run);

  const manualUsedMw = selectManualUsedMw({ manual });

  const modeButtonClass = (active: boolean): string =>
    `flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition ${
      active ? 'bg-emerald-500 text-slate-950' : 'text-slate-400 hover:text-slate-200'
    }`;

  return (
    <aside className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-slate-800 bg-slate-950">
      <div className="border-b border-slate-800 px-4 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <SlidersHorizontal className="h-4 w-4 text-emerald-400" /> ML Controls
        </h2>
        <p className="mt-1 text-xs text-slate-500">Параметры полигона и балансировки</p>
      </div>

      <div className="flex-1 space-y-6 px-4 py-4">
        <Section title="Полигон (LandGEM)">
          <NumberField
            label="Накопленные ТБО"
            suffix="т"
            value={inputs.total_legacy_tonnes}
            min={0}
            step={100_000}
            onChange={(v) => updateInputs({ total_legacy_tonnes: v })}
          />
          <NumberField
            label="Приток отходов"
            suffix="т/год"
            value={inputs.annual_inflow_tonnes}
            min={0}
            step={10_000}
            onChange={(v) => updateInputs({ annual_inflow_tonnes: v })}
          />
          <SliderField
            label="Потенциал метана L₀"
            value={inputs.lo_m3_per_tonne}
            min={70}
            max={80}
            step={0.5}
            onChange={(v) => updateInputs({ lo_m3_per_tonne: v })}
            format={(v) => `${fmtNum(v)} м³/т`}
          />
          <SliderField
            label="Скорость разложения k"
            value={inputs.k_per_year}
            min={0.02}
            max={0.04}
            step={0.001}
            onChange={(v) => updateInputs({ k_per_year: v })}
            format={(v) => `${v.toFixed(3)} 1/год`}
          />
          <SliderField
            label="Доля CH₄ в газе"
            value={inputs.methane_fraction}
            min={0.45}
            max={0.6}
            step={0.01}
            onChange={(v) => updateInputs({ methane_fraction: v })}
            format={(v) => `${Math.round(v * 100)} %`}
          />
          <SliderField
            label="Горизонт прогноза"
            value={inputs.horizon_years}
            min={10}
            max={20}
            step={1}
            onChange={(v) => updateInputs({ horizon_years: v })}
            format={(v) => `${v} лет`}
          />
        </Section>

        <Section title="Газ и рынок">
          <SliderField
            label="Сероводород H₂S"
            value={h2sPpm}
            min={5}
            max={150}
            step={1}
            onChange={setH2sPpm}
            format={(v) => `${v} ppm`}
          />
          <NumberField
            label="Курс BTC"
            suffix="USD"
            value={market.btc_price}
            min={1000}
            step={1000}
            onChange={(v) => updateMarket({ btc_price: v })}
          />
          <NumberField
            label="Аренда GPU"
            suffix="$/GPU·ч"
            value={market.gpu_rent_usd_per_gpu_hour}
            min={0.1}
            step={0.1}
            onChange={(v) => updateMarket({ gpu_rent_usd_per_gpu_hour: v })}
          />
          <NumberField
            label="Наработка ГПУ"
            suffix="мес"
            value={monthsOperated}
            min={0}
            max={120}
            onChange={setMonthsOperated}
          />
        </Section>

        <Section title="Источник рынка">
          <select
            value={marketProvider}
            onChange={(event) => setMarketProvider(event.target.value as MarketProvider)}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
          >
            <option value="synthetic">Синтетика (детерминизм)</option>
            <option value="auto">Auto: live → синтетика</option>
            <option value="live">Live: CoinGecko + mempool.space</option>
          </select>
          {marketQuote ? (
            <p className="text-[11px] leading-snug text-slate-500">
              Источник:{' '}
              <b className={marketQuote.source === 'live' ? 'text-emerald-300' : 'text-slate-300'}>
                {marketQuote.source === 'live' ? 'live' : 'синтетика'}
              </b>
              {marketQuote.source === 'live'
                ? ` · BTC $${fmtNum(marketQuote.btc_price_usd, 0)}`
                : ''}
              {marketQuote.network_hashrate_ths
                ? ` · ${fmtNum(marketQuote.network_hashrate_ths / 1e6, 1)} EH/s`
                : ''}
            </p>
          ) : null}
          <p className="text-[11px] leading-snug text-slate-600">
            В live-режиме курс BTC и хешрейт берутся с публичных API; при сбое — откат на синтетику с пометкой.
          </p>
        </Section>

        <Section title="Налоговый режим КР">
          <select
            value={fiscalRegime}
            onChange={(event) => setFiscalRegime(event.target.value as FiscalRegime)}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
          >
            <option value="kr_htp">ПВТ: 1 % выручки IT, майнинг отдельно</option>
            <option value="kz_aifc">Astana Hub (KZ): сравнение режимов</option>
            <option value="kr_general">Общий: прибыль 10 % + майнинг-налог</option>
            <option value="none">Без налогов (pretax)</option>
          </select>
        </Section>

        <Section title="Режим распределения">
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-700 bg-slate-900 p-1">
            <button type="button" onClick={() => setMode('manual')} className={modeButtonClass(mode === 'manual')}>
              <SlidersHorizontal className="h-3.5 w-3.5" /> Manual
            </button>
            <button type="button" onClick={() => setMode('auto')} className={modeButtonClass(mode === 'auto')}>
              <Bot className="h-3.5 w-3.5" /> AI Auto
            </button>
          </div>

          {mode === 'manual' ? (
            <div className="space-y-3 rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
              <SliderField
                label="Antminer S19 Pro"
                value={manual.miners}
                min={0}
                max={2000}
                step={10}
                onChange={(v) => setManual({ miners: v })}
                format={(v) => `${v} шт`}
              />
              <SliderField
                label="ИИ-серверы"
                value={manual.aiServers}
                min={0}
                max={1000}
                step={10}
                onChange={(v) => setManual({ aiServers: v })}
                format={(v) => `${v} шт`}
              />
              <p className="text-xs text-slate-500">
                Потребление парка: {fmtNum(manualUsedMw, 2)} МВт (с PUE {PUE_DC})
              </p>
            </div>
          ) : (
            <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs leading-relaxed text-emerald-200/80">
              ML-балансировщик распределит мощность по марже на кВт·день, учтёт прогноз BTC
              и отключит наименее маржинальные узлы при падении качества газа.
            </p>
          )}
        </Section>
      </div>

      <div className="space-y-2 border-t border-slate-800 px-4 py-4">
        <button
          type="button"
          onClick={() => void run()}
          disabled={running}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? 'Симуляция…' : 'Запустить симуляцию'}
        </button>
        <button
          type="button"
          onClick={resetToBishkekDefaults}
          disabled={running}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 transition hover:border-slate-500 hover:text-slate-100 disabled:opacity-60"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Дефолты Бишкека (20 Мт · L₀ 75 · k 0.03)
        </button>
      </div>
    </aside>
  );
}
