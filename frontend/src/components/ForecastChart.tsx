import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useSimulation } from '../store/simulationStore';
import { fmtNum } from '../utils/format';
import { useIsPhone } from '../utils/useMediaQuery';
import { Card, CardTitle, ChartTooltip, LegendChip, Spinner } from './primitives';

export function ForecastChart(): JSX.Element {
  const forecast = useSimulation((s) => s.forecast);
  const status = useSimulation((s) => s.status.forecast);
  const isPhone = useIsPhone();

  const data = (forecast?.annual ?? []).map((point) => ({
    label: point.label,
    landgem: point.landgem_ch4_m3 / 1_000_000,
    forecast: point.forecast_ch4_m3 / 1_000_000,
    // Приём Recharts для CI-бэнда: стек «невидимая база + ширина»
    ciBase: point.ci_lower / 1_000_000,
    ciWidth: Math.max(0, point.ci_upper - point.ci_lower) / 1_000_000,
  }));

  return (
    <Card className="min-w-0">
      <CardTitle
        right={
          forecast ? (
            <span className="text-xs text-slate-500 sm:text-[11px]">
              модель: {forecast.meta.model} · ρ(AR1) = {forecast.meta.ar1_rho} · горизонт{' '}
              {forecast.annual.length} лет
            </span>
          ) : null
        }
      >
        Прогноз метана: LandGEM + ML-сезонность
      </CardTitle>

      {data.length === 0 ? (
        <div className="flex h-64 items-center justify-center gap-2 text-sm text-slate-500 sm:h-72">
          {status === 'loading' ? (
            <>
              <Spinner /> Считаем прогноз…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-2 sm:gap-3">
            <LegendChip color="#64748b" label="LandGEM (физическая база)" dashed />
            <LegendChip color="#10b981" label="ML-прогноз с сезонностью" />
            <LegendChip color="rgba(16,185,129,0.30)" label="95 % доверительный интервал" />
          </div>
          <div className="h-64 sm:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  stroke="#475569"
                  tick={{ fill: '#94a3b8', fontSize: isPhone ? 11 : 10 }}
                  tickLine={false}
                  minTickGap={isPhone ? 26 : 18}
                />
                <YAxis
                  stroke="#475569"
                  tick={{ fill: '#94a3b8', fontSize: isPhone ? 12 : 11 }}
                  tickLine={false}
                  width={isPhone ? 48 : 44}
                  tickFormatter={(value: number) => fmtNum(value, 0)}
                />
                <Tooltip
                  content={<ChartTooltip unit="млн м³ CH₄/год" />}
                  cursor={{ stroke: '#334155' }}
                />
                <Area
                  dataKey="ciBase"
                  stackId="ci"
                  stroke="none"
                  fill="transparent"
                  isAnimationActive={false}
                />
                <Area
                  dataKey="ciWidth"
                  stackId="ci"
                  stroke="none"
                  fill="#10b981"
                  fillOpacity={0.2}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="landgem"
                  name="LandGEM (база)"
                  stroke="#64748b"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="ML-прогноз"
                  stroke="#10b981"
                  strokeWidth={2.5}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-slate-500 sm:text-[11px]">
            млн м³ CH₄/год. Сезонность: осенний пик влажности (мокрые бахчевые) повышает
            волатильность генерации — её учитывает Smart Load Balancing.
          </p>
        </>
      )}
    </Card>
  );
}
