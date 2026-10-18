/** Форматирование чисел для дашборда (ru-RU). */

const isFiniteNumber = (value: number | null | undefined): value is number =>
  typeof value === 'number' && Number.isFinite(value);

export function fmtNum(value: number | null | undefined, digits = 1): string {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
}

export function fmtInt(value: number | null | undefined): string {
  return fmtNum(value, 0);
}

export function fmtUsd(value: number | null | undefined, digits = 0): string {
  if (!isFiniteNumber(value)) return '—';
  const sign = value < 0 ? '−' : '';
  return `${sign}$${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(Math.abs(value))}`;
}

export function fmtMln(value: number | null | undefined, digits = 1): string {
  if (!isFiniteNumber(value)) return '—';
  return `${fmtNum(value / 1_000_000, digits)} млн`;
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('ru-RU', {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
}

export function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
