import { GitBranch } from 'lucide-react';
import { useSimulation } from '../store/simulationStore';
import { fmtNum, fmtPercent, fmtUsd } from '../utils/format';
import { Badge, Card, CardTitle, Spinner } from './primitives';

export function PlanPanel(): JSX.Element {
  const plan = useSimulation((s) => s.plan);
  const status = useSimulation((s) => s.status.plan);

  if (!plan) {
    return (
      <Card>
        <CardTitle>План на 12 месяцев (упреждающий DP)</CardTitle>
        <div className="flex h-24 items-center justify-center gap-2 text-sm text-slate-500">
          {status === 'loading' ? (
            <>
              <Spinner /> Считаем многошаговый план…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      </Card>
    );
  }

  const rows = plan.plan;
  const maxAi = Math.max(...rows.map((r) => r.ai_servers));
  const maxMiners = Math.max(...rows.map((r) => r.miners));
  const avgReserve = rows.reduce((acc, r) => acc + r.reserve_share, 0) / rows.length;
  const gainPct =
    plan.totals.naive_net_usd !== 0
      ? plan.totals.improvement_usd / Math.abs(plan.totals.naive_net_usd)
      : 0;

  return (
    <Card>
      <CardTitle
        right={
          <Badge tone={plan.totals.improvement_usd > 0 ? 'green' : 'slate'}>
            DP vs наивный план
          </Badge>
        }
      >
        План на 12 месяцев (упреждающий DP)
      </CardTitle>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">Рекомендуемый парк</p>
          <p className="mt-1 text-lg font-bold text-slate-100">
            {maxAi} ИИ · {maxMiners} ASIC
          </p>
          <p className="text-[11px] text-slate-500">максимум по месяцам горизонта</p>
        </div>
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">Выигрыш vs наивный</p>
          <p className={`mt-1 text-lg font-bold ${plan.totals.improvement_usd > 0 ? 'text-emerald-300' : 'text-slate-300'}`}>
            {fmtUsd(plan.totals.improvement_usd)}
          </p>
          <p className="text-[11px] text-slate-500">{fmtPercent(gainPct)} к чистому результату</p>
        </div>
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">Резерв мощности</p>
          <p className="mt-1 text-lg font-bold text-amber-300">{fmtPercent(avgReserve)}</p>
          <p className="text-[11px] text-slate-500">
            база {fmtPercent(plan.reserve_policy.base_share, 0)} → пик{' '}
            {fmtPercent(plan.reserve_policy.max_share, 0)}
          </p>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-700 text-[11px] uppercase tracking-wider text-slate-500">
              <th className="py-1.5 pr-2 font-medium">Мес</th>
              <th className="py-1.5 pr-2 text-right font-medium">МВт</th>
              <th className="py-1.5 pr-2 text-right font-medium">ИИ</th>
              <th className="py-1.5 pr-2 text-right font-medium">ASIC</th>
              <th className="py-1.5 pr-2 text-right font-medium">Резерв</th>
              <th className="py-1.5 text-right font-medium">Маржа/сут</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.month} className="border-b border-slate-800/70 text-slate-300">
                <td className="py-1 pr-2 text-slate-500">{row.month}</td>
                <td className="py-1 pr-2 text-right">{fmtNum(row.allocatable_mw, 2)}</td>
                <td className="py-1 pr-2 text-right">{row.ai_servers}</td>
                <td className="py-1 pr-2 text-right">{row.miners}</td>
                <td className="py-1 pr-2 text-right text-amber-300/90">
                  {fmtPercent(row.reserve_share, 0)}
                </td>
                <td className="py-1 text-right">{fmtUsd(row.margin_usd_day)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1">
          <GitBranch className="h-3.5 w-3.5" /> переключений: {plan.switch_events.length}
        </span>
        <span>стоимость переключений: {fmtUsd(plan.switching_costs.total_usd)}</span>
        <span>
          маржа план/наив: {fmtUsd(plan.totals.optimized_net_usd)} / {fmtUsd(plan.totals.naive_net_usd)}
        </span>
      </p>
    </Card>
  );
}
