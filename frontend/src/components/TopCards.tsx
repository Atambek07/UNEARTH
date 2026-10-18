import type { ReactNode } from 'react';
import { HeartPulse, Loader2, Server, TreePine, Zap } from 'lucide-react';
import { useSimulation } from '../store/simulationStore';
import { fmtInt, fmtNum, fmtUsd } from '../utils/format';
import { Card } from './primitives';

type Tone = 'emerald' | 'amber' | 'red' | 'sky';

const TONE_STYLES: Record<Tone, { value: string; icon: string }> = {
  emerald: { value: 'text-emerald-300', icon: 'bg-emerald-500/10 text-emerald-400' },
  amber: { value: 'text-amber-300', icon: 'bg-amber-500/10 text-amber-400' },
  red: { value: 'text-red-300', icon: 'bg-red-500/10 text-red-400' },
  sky: { value: 'text-sky-300', icon: 'bg-sky-500/10 text-sky-400' },
};

function StatCard({
  icon,
  title,
  value,
  sub,
  tone = 'emerald',
}: {
  icon: ReactNode;
  title: string;
  value: ReactNode;
  sub: ReactNode;
  tone?: Tone;
}): JSX.Element {
  const styles = TONE_STYLES[tone];
  return (
    <Card className="flex items-start gap-3">
      <div className={`rounded-lg p-2 ${styles.icon}`}>{icon}</div>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{title}</p>
        <p className={`mt-1 text-xl font-bold leading-tight ${styles.value}`}>{value}</p>
        <p className="mt-1 text-xs leading-snug text-slate-400">{sub}</p>
      </div>
    </Card>
  );
}

export function TopCards(): JSX.Element {
  const forecast = useSimulation((s) => s.forecast);
  const optimize = useSimulation((s) => s.optimize);
  const maintenance = useSimulation((s) => s.maintenance);
  const finance = useSimulation((s) => s.finance);
  const running = useSimulation((s) => s.running);

  if (!forecast) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <Card key={index} className="flex h-[104px] items-center gap-2 text-sm text-slate-500">
            <Loader2 className={`h-4 w-4 text-emerald-400 ${running ? 'animate-spin' : ''}`} />
            {running ? 'Расчёт симуляции…' : 'Нажмите «Запустить симуляцию»'}
          </Card>
        ))}
      </div>
    );
  }

  const miners = optimize?.allocation.find((r) => r.node_type === 'antminer_s19_pro')?.count ?? 0;
  const aiServers = optimize?.allocation.find((r) => r.node_type === 'ai_server')?.count ?? 0;
  const health = maintenance?.fleet_health_score;
  const healthTone: Tone = health === undefined ? 'emerald' : health >= 80 ? 'emerald' : health >= 50 ? 'amber' : 'red';

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        icon={<Zap className="h-5 w-5" />}
        title="Генерация (год 1)"
        value={`${fmtNum(forecast.summary.year1_avg_power_mw, 2)} МВт`}
        sub={`${fmtInt(forecast.summary.year1_energy_mwh)} МВт·ч/год · пик ${fmtNum(forecast.summary.peak_power_mw, 2)} МВт`}
      />
      <StatCard
        icon={<Server className="h-5 w-5" />}
        title="Серверы в работе"
        value={`${fmtInt(aiServers)} ИИ · ${fmtInt(miners)} ASIC`}
        sub={`Выделено ${fmtNum(optimize?.used_mw ?? 0, 2)} из ${fmtNum(optimize?.allocatable_mw ?? 0, 2)} МВт мощности`}
        tone="sky"
      />
      <StatCard
        icon={<HeartPulse className="h-5 w-5" />}
        title="Health Score ГПУ"
        value={health !== undefined ? `${fmtNum(health)} %` : '—'}
        sub={
          maintenance
            ? `${maintenance.genset_count} × Jenbacher · слабейший ${maintenance.weakest.id}: ресурс ${fmtNum(
                maintenance.weakest.rul_months,
                0,
              )} мес`
            : 'Расчёт обслуживания…'
        }
        tone={healthTone}
      />
      <StatCard
        icon={<TreePine className="h-5 w-5" />}
        title="Green Tracker"
        value={finance ? `${fmtInt(finance.totals.co2_avoided_t)} т CO₂-экв.` : '—'}
        sub={
          finance
            ? `Фонд озеленения ${fmtUsd(finance.totals.green_fund_usd)} → ${fmtInt(
                finance.totals.trees_planted,
              )} саженцев (5 % прибыли)`
            : 'Расчёт экоэффекта…'
        }
      />
    </div>
  );
}
