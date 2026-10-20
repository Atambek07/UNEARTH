import { Bot, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react';
import { PUE_DC, selectManualUsedMw, useSimulation } from '../store/simulationStore';
import { fmtInt, fmtNum, fmtPercent, fmtUsd } from '../utils/format';
import { Badge, Card, CardTitle, Spinner } from './primitives';

export function AllocationPanel(): JSX.Element {
  const optimize = useSimulation((s) => s.optimize);
  const mode = useSimulation((s) => s.mode);
  const manual = useSimulation((s) => s.manual);
  const status = useSimulation((s) => s.status.optimize);

  if (!optimize) {
    return (
      <Card>
        <CardTitle>Распределение мощности (Smart Grid)</CardTitle>
        <div className="flex h-24 items-center justify-center gap-2 text-sm text-slate-500">
          {status === 'loading' ? (
            <>
              <Spinner /> Балансируем нагрузку…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      </Card>
    );
  }

  const manualUsedMw = selectManualUsedMw({ manual });

  return (
    <Card className="min-w-0">
      <CardTitle
        right={
          <Badge tone={optimize.manual ? 'sky' : 'green'}>
            {optimize.manual ? 'Manual Allocation' : 'AI Auto-Optimize'}
          </Badge>
        }
      >
        Распределение мощности (Smart Grid)
      </CardTitle>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          {optimize.allocation.map((row) => (
            <div key={row.node_type} className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-200">{row.label}</span>
                <Badge tone={row.status === 'running' ? 'green' : 'slate'}>
                  {row.status === 'running' ? 'работает' : 'не задействован'}
                </Badge>
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                <div>
                  <dt className="text-slate-500">Узлов</dt>
                  <dd className="font-semibold text-slate-200">{fmtInt(row.count)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Мощность</dt>
                  <dd className="font-semibold text-slate-200">{fmtNum(row.power_mw, 2)} МВт</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Выручка</dt>
                  <dd className="font-semibold text-slate-200">{fmtUsd(row.revenue_usd_day)}/д</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Маржа</dt>
                  <dd className="font-semibold text-emerald-300">{fmtUsd(row.margin_usd_day)}/д</dd>
                </div>
              </dl>
            </div>
          ))}

          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-700/70 bg-slate-900/60 px-3 py-2 text-xs text-slate-400">
            <span>
              Использовано:{' '}
              <b className="text-slate-200">{fmtNum(optimize.used_mw, 2)} МВт</b> из{' '}
              {fmtNum(optimize.allocatable_mw, 2)} МВт
            </span>
            <span>
              Свободный резерв:{' '}
              <b className="text-slate-200">{fmtNum(optimize.curtailed_mw, 2)} МВт</b>
            </span>
          </div>

          {optimize.overcommitted && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs leading-relaxed text-red-200">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              Перегруз: ручное распределение ({fmtNum(manualUsedMw, 2)} МВт с PUE {PUE_DC})
              превышает доступную мощность. Уменьшите парк или включите AI Auto-Optimize.
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Bot className="h-3.5 w-3.5 text-emerald-400" /> Логика ML-балансировщика
            </p>
            <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-slate-300">
              {optimize.rationale.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          </div>

          <div className="space-y-2 rounded-lg border border-slate-700/70 bg-slate-900/60 p-3 text-xs">
            <div className="flex flex-wrap items-center gap-2 text-slate-400">
              <span>Режим рынка:</span>
              <Badge
                tone={
                  optimize.market.regime === 'bullish'
                    ? 'green'
                    : optimize.market.regime === 'bearish'
                      ? 'red'
                      : 'slate'
                }
              >
                {optimize.market.regime}
              </Badge>
              {optimize.market.regime === 'bearish' && (
                <TrendingDown className="h-4 w-4 text-red-400" />
              )}
              {optimize.market.regime === 'bullish' && (
                <TrendingUp className="h-4 w-4 text-emerald-400" />
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-slate-400">
              <span>ML-прогноз BTC (3 мес)</span>
              <b className={optimize.market.predicted_3m_return < 0 ? 'text-red-300' : 'text-emerald-300'}>
                {fmtPercent(optimize.market.predicted_3m_return)}
              </b>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-slate-400">
              <span>Маржа на кВт·день</span>
              <span>
                ИИ <b className="text-emerald-300">${fmtNum(optimize.margins.ai_usd_per_kw_day, 2)}</b>{' '}
                · майнинг{' '}
                <b className="text-sky-300">${fmtNum(optimize.margins.mining_usd_per_kw_day, 2)}</b>
              </span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-slate-400">
              <span>Derate по качеству газа</span>
              <b className="text-amber-300">×{fmtNum(optimize.quality.derate_factor, 2)}</b>
            </div>
            {optimize.shutdown_order.length > 0 && (
              <p className="text-slate-500">
                Лестница отключений: {optimize.shutdown_order.join(' → ')}
              </p>
            )}
            <p className="text-slate-500">
              Режим: {mode === 'auto' ? 'AI Auto-Optimize' : 'Manual Allocation'}
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}
