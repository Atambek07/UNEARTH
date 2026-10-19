import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useSimulation } from '../store/simulationStore';
import { fmtNum, fmtPercent, fmtUsd } from '../utils/format';
import { Card, CardTitle, ChartTooltip, LegendChip, Spinner } from './primitives';

export function FinanceChart(): JSX.Element {
  const finance = useSimulation((s) => s.finance);
  const status = useSimulation((s) => s.status.finance);

  const data = finance?.chart ?? [];

  return (
    <Card>
      <CardTitle
        right={
          finance ? (
            <span className="text-[11px] text-slate-500">
              CAPEX {fmtUsd(finance.capex_total_usd)} · окупаемость:{' '}
              {finance.payback_years !== null ? `${fmtNum(finance.payback_years)} г` : 'за горизонтом'} ·
              IRR: {finance.irr !== null ? fmtPercent(finance.irr) : '—'} · налоги:{' '}
              {fmtUsd(finance.fiscal?.totals.taxes_total_usd ?? 0)}
            </span>
          ) : null
        }
      >
        Финансовая эффективность (Монте-Карло)
      </CardTitle>

      {data.length === 0 ? (
        <div className="flex h-72 items-center justify-center gap-2 text-sm text-slate-500">
          {status === 'loading' ? (
            <>
              <Spinner /> Считаем финансовую модель…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-3">
            <LegendChip color="#f43f5e" label="CAPEX" />
            <LegendChip color="#f59e0b" label="OPEX" />
            <LegendChip color="#10b981" label="Чистая прибыль (P50)" />
            <LegendChip color="#38bdf8" label="Кумулятивный поток (диск.)" />
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  stroke="#475569"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickLine={false}
                />
                <YAxis
                  stroke="#475569"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickLine={false}
                  width={56}
                  tickFormatter={(value: number) => `${(value / 1_000_000).toFixed(0)} млн`}
                />
                <Tooltip
                  content={<ChartTooltip unit="$" formatter={(value) => fmtUsd(value)} />}
                  cursor={{ fill: 'rgba(51,65,85,0.25)' }}
                />
                <ReferenceLine y={0} stroke="#475569" />
                <Bar dataKey="capex_usd" name="CAPEX" fill="#f43f5e" fillOpacity={0.7} radius={[3, 3, 0, 0]} />
                <Bar dataKey="opex_usd" name="OPEX" fill="#f59e0b" fillOpacity={0.75} radius={[3, 3, 0, 0]} />
                <Bar
                  dataKey="net_profit_p50_usd"
                  name="Чистая прибыль (P50)"
                  fill="#10b981"
                  fillOpacity={0.85}
                  radius={[3, 3, 0, 0]}
                />
                <Line
                  type="monotone"
                  dataKey="cumulative_cashflow_p50_usd"
                  name="Кумулятивный поток"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            Диапазон P10–P90 чистой прибыли и волатильность рынка — в ответе API
            (<code>annual[].net_profit_p10_usd / p90</code>); на графике — медиана P50.
          </p>
        </>
      )}
    </Card>
  );
}
