import type { ReactNode } from 'react';

export function Card({ children, className = '' }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <div
      className={`rounded-xl border border-slate-700/70 bg-slate-800/60 p-3 shadow-lg shadow-black/20 sm:p-4 ${className}`}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  right,
}: {
  children: ReactNode;
  right?: ReactNode;
}): JSX.Element {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 sm:mb-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 sm:text-[11px]">{children}</h3>
      {right}
    </div>
  );
}

export function Spinner({ className = 'h-4 w-4' }: { className?: string }): JSX.Element {
  return (
    <span
      aria-hidden
      className={`inline-block animate-spin rounded-full border-2 border-slate-600 border-t-emerald-400 ${className}`}
    />
  );
}

export function LegendChip({
  color,
  label,
  dashed = false,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}): JSX.Element {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
      {dashed ? (
        <span className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: color }} />
      ) : (
        <span className="h-2 w-4 rounded-sm" style={{ background: color }} />
      )}
      {label}
    </span>
  );
}

export type BadgeTone = 'green' | 'amber' | 'red' | 'slate' | 'sky';

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }): JSX.Element {
  const tones: Record<BadgeTone, string> = {
    green: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    red: 'bg-red-500/15 text-red-300 border-red-500/30',
    slate: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
    sky: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium sm:text-[11px] ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** Строка payload из Recharts (структурно совместимо с Payload<TValue, TName>). */
interface TooltipRow {
  name?: string | number;
  value?: number | string;
  color?: string;
  dataKey?: string | number;
}

/**
 * Кастомный тултип Recharts: скрывает служебные ключи CI-бэнда
 * (ciBase/ciWidth) и форматирует значения.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  unit,
  formatter,
}: {
  active?: boolean;
  payload?: TooltipRow[];
  label?: string | number;
  unit: string;
  formatter?: (value: number) => string;
}): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  const rows = payload.filter(
    (row) => row.dataKey !== 'ciBase' && row.dataKey !== 'ciWidth' && row.value !== undefined,
  );
  return (
    <div className="max-w-[min(20rem,80vw)] rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs shadow-xl">
      {label !== undefined && <div className="mb-1 font-semibold text-slate-300">{label}</div>}
      {rows.map((row, index) => (
        <div key={`${row.dataKey ?? row.name ?? index}`} className="flex items-center gap-2 py-0.5">
          <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: row.color ?? '#475569' }} />
          <span className="text-slate-400">{row.name}</span>
          <span className="ml-auto pl-4 font-medium text-slate-100">
            {formatter && typeof row.value === 'number'
              ? formatter(row.value)
              : `${row.value} ${unit}`}
          </span>
        </div>
      ))}
    </div>
  );
}
