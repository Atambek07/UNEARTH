import { useSimulation } from '../store/simulationStore';
import { fmtNum, fmtPercent, fmtUsd } from '../utils/format';
import { Card, CardTitle, Spinner } from './primitives';

const HEALTH_BAR = {
  healthy: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  critical: 'bg-red-500',
} as const;

const HEALTH_TEXT = {
  healthy: 'text-emerald-300',
  degraded: 'text-amber-300',
  critical: 'text-red-300',
} as const;

function Row({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-200">{value}</span>
    </div>
  );
}

export function MaintenancePanel(): JSX.Element {
  const maintenance = useSimulation((s) => s.maintenance);
  const status = useSimulation((s) => s.status.maintenance);

  if (!maintenance) {
    return (
      <Card>
        <CardTitle>Предиктивное обслуживание (H₂S → износ Jenbacher)</CardTitle>
        <div className="flex h-24 items-center justify-center gap-2 text-sm text-slate-500">
          {status === 'loading' ? (
            <>
              <Spinner /> Считаем износ и OPEX…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      </Card>
    );
  }

  const opexLines: Record<string, number> = {
  Скрубберы: maintenance.opex_monthly_usd.scrubbing_usd,
  Расходники: maintenance.opex_monthly_usd.consumables_usd,
  ФОТ: maintenance.opex_monthly_usd.labor_usd,
  Страхование: maintenance.opex_monthly_usd.insurance_usd,
  "Амортизация станции": maintenance.opex_monthly_usd.plant_depreciation_usd,
  "Резерв капремонтов": maintenance.opex_monthly_usd.overhaul_reserve_usd,
};

  return (
    <Card className="min-w-0">
      <CardTitle
        right={
          <span className="text-xs text-slate-500 sm:text-[11px]">
            износ {fmtNum(maintenance.wear_pct_month, 2)} %/мес при H₂S{' '}
            {fmtNum(maintenance.gas.h2s_ppm, 0)} ppm
          </span>
        }
      >
        Предиктивное обслуживание (H₂S → износ Jenbacher)
      </CardTitle>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {maintenance.generators.map((generator) => (
            <div
              key={generator.id}
              className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3"
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-200">{generator.id}</span>
                <span className={HEALTH_TEXT[generator.status]}>
                  {fmtNum(generator.health_score)} %
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div
                  className={`h-full rounded-full ${HEALTH_BAR[generator.status]}`}
                  style={{ width: `${Math.min(100, Math.max(2, generator.health_score))}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-500 sm:text-[11px]">
                ресурс ≈ {fmtNum(generator.rul_months, 0)} мес · риск отказа 12 мес:{' '}
                {fmtPercent(generator.failure_risk_12m, 0)}
              </p>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3 text-xs">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400 sm:text-[11px]">
            Скрубберы и OPEX
          </p>
          <Row label="Ресурс сорбента" value={`${fmtNum(maintenance.scrubber.life_months, 1)} мес`} />
          <Row label="Замен в год" value={fmtNum(maintenance.scrubber.replacements_per_year, 1)} />
          <Row
            label="Стоимость замен"
            value={`${fmtUsd(maintenance.scrubber.annual_cost_usd)}/год`}
          />
          <Row
            label="Загрузка серы"
            value={`${fmtNum(maintenance.gas.sulfur_load_kg_month, 1)} кг/мес`}
          />

          <div className="mt-2 border-t border-slate-800 pt-2">
            {Object.entries(opexLines).map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-2 py-0.5">
                <span className="text-slate-500">{label}</span>
                <span className="text-slate-300">{fmtUsd(value)}/мес</span>
              </div>
            ))}
            <div className="mt-1 flex items-center justify-between gap-2 border-t border-slate-800 pt-1 font-semibold">
              <span className="text-slate-300">Итого OPEX</span>
              <span className="text-slate-100">{fmtUsd(maintenance.opex_monthly_usd.total_usd)}/мес</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
