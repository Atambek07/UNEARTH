import { Leaf } from 'lucide-react';
import { useSimulation } from '../store/simulationStore';
import { fmtInt, fmtNum, fmtUsd } from '../utils/format';
import { Badge, Card, CardTitle, Spinner } from './primitives';

export function CarbonPanel(): JSX.Element {
  const carbon = useSimulation((s) => s.carbon);
  const status = useSimulation((s) => s.status.carbon);

  if (!carbon) {
    return (
      <Card>
        <CardTitle>Карбоновый модуль (ACM0001)</CardTitle>
        <div className="flex h-24 items-center justify-center gap-2 text-sm text-slate-500">
          {status === 'loading' ? (
            <>
              <Spinner /> Считаем углеродные кредиты…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      </Card>
    );
  }

  const p50 = carbon.scenarios.p50;
  const p10 = carbon.scenarios.p10;
  const p90 = carbon.scenarios.p90;
  const yearsShown = carbon.annual.slice(0, 5);

  return (
    <Card className="min-w-0">
      <CardTitle
        right={
          <Badge tone="green">
            <Leaf className="mr-1 h-3 w-3" /> {carbon.methodology.split('(')[0].trim()}
          </Badge>
        }
      >
        Карбоновый модуль (углеродные кредиты)
      </CardTitle>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-xs uppercase tracking-wider text-slate-500 sm:text-[11px]">Кредиты (net)</p>
          <p className="mt-1 text-lg font-bold text-emerald-300">
            {fmtInt(carbon.totals.net_credits_t)} т
          </p>
          <p className="text-xs text-slate-500 sm:text-[11px]">
            буфер {fmtInt(carbon.totals.buffer_credits_t)} т · CH₄{' '}
            {fmtInt(carbon.totals.ch4_destroyed_t)} т
          </p>
        </div>
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-xs uppercase tracking-wider text-slate-500 sm:text-[11px]">NPV, P50</p>
          <p className="mt-1 text-lg font-bold text-slate-100">{fmtUsd(p50.npv_usd)}</p>
          <p className="text-xs text-slate-500 sm:text-[11px]">
            цена {fmtUsd(p50.price_usd_per_t)}/т · лаг {carbon.params.verification_lag_months} мес
          </p>
        </div>
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-xs uppercase tracking-wider text-slate-500 sm:text-[11px]">Выручка, P50</p>
          <p className="mt-1 text-lg font-bold text-slate-100">{fmtUsd(p50.total_revenue_usd)}</p>
          <p className="text-xs text-slate-500 sm:text-[11px]">
            P10–P90: {fmtUsd(p10.total_revenue_usd)} – {fmtUsd(p90.total_revenue_usd)}
          </p>
        </div>
      </div>

      <div className="-mx-1 mt-3 overflow-x-auto px-1">
        <table className="w-full min-w-[420px] text-left text-xs tabular-nums">
          <thead>
            <tr className="border-b border-slate-700 text-xs uppercase tracking-wider text-slate-500 sm:text-[11px]">
              <th className="py-1.5 pr-2 font-medium">Год</th>
              <th className="py-1.5 pr-2 text-right font-medium">CH₄, м³</th>
              <th className="py-1.5 pr-2 text-right font-medium">CO₂e, т</th>
              <th className="py-1.5 text-right font-medium">Кредиты, т</th>
            </tr>
          </thead>
          <tbody>
            {yearsShown.map((row) => (
              <tr key={row.year} className="border-b border-slate-800/70 text-slate-300">
                <td className="py-1 pr-2 text-slate-500">{row.year}</td>
                <td className="py-1 pr-2 text-right">{fmtInt(row.ch4_destroyed_m3)}</td>
                <td className="py-1 pr-2 text-right">{fmtInt(row.baseline_co2e_t)}</td>
                <td className="py-1 text-right">{fmtInt(row.net_credits_t)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-500 sm:text-[11px]">
        GWP {fmtNum(carbon.params.gwp, 0)} · буфер {fmtNum(carbon.params.buffer_share * 100, 0)} % ·
        выручка не входит в финансовую модель и не дублирует Фонд озеленения.
      </p>
    </Card>
  );
}
