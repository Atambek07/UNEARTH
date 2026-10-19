import { useEffect, useState } from 'react';
import { Database, GitCompare, Loader2, Save, Trash2 } from 'lucide-react';
import { useSimulation } from '../store/simulationStore';
import type { ScenarioMetrics } from '../types';
import { fmtDateTime, fmtInt, fmtNum, fmtPercent, fmtUsd } from '../utils/format';
import { Badge, Card, CardTitle } from './primitives';

const METRIC_ROWS: Array<{
  key: keyof ScenarioMetrics;
  label: string;
  render: (value: number) => string;
}> = [
  { key: 'year1_avg_power_mw', label: 'Мощность, год 1', render: (v) => `${fmtNum(v, 2)} МВт` },
  { key: 'capex_total_usd', label: 'CAPEX', render: (v) => fmtUsd(v) },
  { key: 'payback_years', label: 'Окупаемость', render: (v) => `${fmtNum(v, 1)} лет` },
  { key: 'irr', label: 'IRR', render: (v) => fmtPercent(v) },
  { key: 'net_profit_p50_usd', label: 'Чистая прибыль P50', render: (v) => fmtUsd(v) },
  { key: 'daily_margin_usd', label: 'Маржа/сутки', render: (v) => fmtUsd(v) },
  { key: 'fleet_health_score', label: 'Health ГПУ', render: (v) => `${fmtNum(v, 1)} %` },
  { key: 'co2_avoided_t', label: 'CO₂-экв.', render: (v) => `${fmtInt(v)} т` },
];

export function ScenarioPanel(): JSX.Element {
  const scenarios = useSimulation((s) => s.scenarios);
  const loading = useSimulation((s) => s.scenariosLoading);
  const saving = useSimulation((s) => s.savingScenario);
  const error = useSimulation((s) => s.scenarioError);
  const compare = useSimulation((s) => s.compare);
  const selected = useSimulation((s) => s.selectedScenarioIds);
  const refresh = useSimulation((s) => s.refreshScenarios);
  const save = useSimulation((s) => s.saveScenario);
  const load = useSimulation((s) => s.loadScenario);
  const remove = useSimulation((s) => s.deleteScenario);
  const toggle = useSimulation((s) => s.toggleScenarioSelected);
  const runCompare = useSimulation((s) => s.compareSelected);
  const clearCompare = useSimulation((s) => s.clearCompare);

  const [name, setName] = useState('');

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSave = async (): Promise<void> => {
    const ok = await save(name);
    if (ok) setName('');
  };

  return (
    <Card>
      <CardTitle
        right={
          <Badge tone="sky">
            <Database className="mr-1 h-3 w-3" /> SQLite/Postgres · {scenarios.length} сценариев
          </Badge>
        }
      >
        Сценарии: сохранение и сравнение
      </CardTitle>

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Название сценария, например «H₂S 90 ppm, BTC 40k»"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void onSave()}
          disabled={saving || !name.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Сохранить прогон
        </button>
      </div>
      <p className="mt-1 text-[11px] text-slate-500">
        Сохраняются параметры и дайджест метрик; сервер прогоняет симуляцию заново и фиксирует результат.
      </p>

      {error ? (
        <p className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </p>
      ) : null}

      {scenarios.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          {loading ? 'Загружаем сценарии…' : 'Пока нет сохранённых сценариев.'}
        </p>
      ) : (
        <div className="mt-3 space-y-1">
          <div className="grid grid-cols-[24px_1fr_110px_120px] gap-2 border-b border-slate-700 pb-1 text-[10px] uppercase tracking-wider text-slate-500">
            <span />
            <span>Название</span>
            <span>Создан</span>
            <span className="text-right">Действия</span>
          </div>
          {scenarios.map((scenario) => {
            const checked = selected.includes(scenario.id);
            return (
              <div
                key={scenario.id}
                className={`grid grid-cols-[24px_1fr_110px_120px] items-center gap-2 rounded px-1 py-1 text-xs ${
                  checked ? 'bg-emerald-500/5' : ''
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(scenario.id)}
                  title="Выбрать для сравнения"
                  className="h-4 w-4 accent-emerald-500"
                />
                <span className="truncate text-slate-200">{scenario.name}</span>
                <span className="text-[11px] text-slate-500">{fmtDateTime(scenario.created_at)}</span>
                <span className="flex justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => void load(scenario.id)}
                    className="rounded border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300 hover:border-slate-500 hover:text-slate-100"
                  >
                    Загрузить
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(scenario.id)}
                    className="rounded border border-slate-700 px-1.5 py-0.5 text-[11px] text-red-300 hover:border-red-500/60"
                    title="Удалить сценарий"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void runCompare()}
          disabled={selected.length < 2}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 transition hover:border-slate-500 disabled:opacity-50"
        >
          <GitCompare className="h-3.5 w-3.5" /> Сравнить выбранные ({selected.length})
        </button>
        {compare ? (
          <button
            type="button"
            onClick={clearCompare}
            className="text-xs text-slate-500 underline-offset-2 hover:text-slate-300 hover:underline"
          >
            сбросить сравнение
          </button>
        ) : null}
      </div>

      {compare ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-[10px] uppercase tracking-wider text-slate-500">
                <th className="py-1.5 pr-2 font-medium">Метрика</th>
                {compare.comparison.map((item) => (
                  <th key={item.id} className="py-1.5 pr-2 text-right font-medium">
                    {item.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRIC_ROWS.map(({ key, label, render }) => (
                <tr key={String(key)} className="border-b border-slate-800/70">
                  <td className="py-1 pr-2 text-slate-500">{label}</td>
                  {compare.comparison.map((item) => {
                    const raw = item.metrics[key];
                    const value = typeof raw === 'number' ? raw : null;
                    const isBest = compare.best[String(key)] === item.id;
                    return (
                      <td
                        key={item.id}
                        className={`py-1 pr-2 text-right ${
                          isBest ? 'font-semibold text-emerald-300' : 'text-slate-300'
                        }`}
                      >
                        {value === null ? '—' : render(value)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {compare.missing_ids.length > 0 ? (
            <p className="mt-1 text-[11px] text-amber-300">
              Не найдены сценарии: {compare.missing_ids.join(', ')}
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
