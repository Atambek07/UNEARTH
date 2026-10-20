import { useSimulation } from '../store/simulationStore';
import type { Sector, SectorStatus } from '../types';
import { fmtNum, fmtPercent } from '../utils/format';
import { Badge, type BadgeTone, Card, CardTitle, LegendChip, Spinner } from './primitives';

const STATUS_COLOR: Record<SectorStatus, string> = {
  green: 'bg-emerald-500',
  amber: 'bg-amber-500',
  red: 'bg-red-500',
  depleted: 'bg-slate-600',
};

const STATUS_HEX: Record<SectorStatus, string> = {
  green: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
  depleted: '#475569',
};

const STATUS_LABEL: Record<SectorStatus, string> = {
  green: 'Стабильный газ',
  amber: 'Усиленная фильтрация',
  red: 'Высокий H₂S',
  depleted: 'Выработан',
};

const STATUS_TONE: Record<SectorStatus, BadgeTone> = {
  green: 'green',
  amber: 'amber',
  red: 'red',
  depleted: 'slate',
};

const AGE_LABEL: Record<Sector['age_class'], string> = {
  fresh: 'свежий',
  mid: 'средний',
  old: 'старый',
};

export function SectorMap(): JSX.Element {
  const sectorsData = useSimulation((s) => s.sectors);
  const selectedId = useSimulation((s) => s.selectedSectorId);
  const setSelectedSector = useSimulation((s) => s.setSelectedSector);
  const status = useSimulation((s) => s.status.sectors);

  const sectors = sectorsData?.sectors ?? [];
  const maxFlux = Math.max(1, ...sectors.map((s) => s.ch4_flux_m3_h));
  const selected = sectors.find((s) => s.id === selectedId) ?? null;

  return (
    <Card className="min-w-0">
      <CardTitle
        right={
          sectorsData ? (
            <span className="text-xs text-slate-500 sm:text-[11px]">
              месяц: {sectorsData.month} · статусы предсказывает RandomForest
            </span>
          ) : null
        }
      >
        Карта секторов полигона ({sectors.length || 48})
      </CardTitle>

      {sectors.length === 0 ? (
        <div className="flex h-56 items-center justify-center gap-2 text-sm text-slate-500">
          {status === 'loading' ? (
            <>
              <Spinner /> Строим карту секторов…
            </>
          ) : (
            'Нет данных — запустите симуляцию'
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
          <div>
            <div
              className="grid gap-1 sm:gap-1.5"
              style={{ gridTemplateColumns: `repeat(${sectorsData?.cols ?? 8}, minmax(0, 1fr))` }}
            >
              {sectors.map((sector) => (
                <button
                  key={sector.id}
                  type="button"
                  title={`${sector.id} · ${sector.note} · H₂S ${fmtNum(sector.h2s_ppm)} ppm · ${fmtNum(
                    sector.ch4_flux_m3_h,
                  )} м³/ч`}
                  aria-label={`${sector.id}: ${STATUS_LABEL[sector.status]}`}
                  onClick={() => setSelectedSector(sector.id === selectedId ? null : sector.id)}
                  className={`aspect-square rounded-sm transition hover:ring-2 hover:ring-slate-300/70 sm:rounded-md ${
                    STATUS_COLOR[sector.status]
                  } ${sector.id === selectedId ? 'ring-2 ring-white' : ''}`}
                  style={{ opacity: 0.45 + 0.55 * Math.min(1, sector.ch4_flux_m3_h / maxFlux) }}
                />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2 sm:gap-3">
              {(Object.keys(STATUS_COLOR) as SectorStatus[]).map((key) => (
                <LegendChip key={key} color={STATUS_HEX[key]} label={STATUS_LABEL[key]} />
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-3 text-sm">
            {selected ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-100">{selected.id}</span>
                  <Badge tone={STATUS_TONE[selected.status]}>{STATUS_LABEL[selected.status]}</Badge>
                </div>
                <p className="text-xs leading-snug text-slate-400">{selected.note}</p>
                <dl className="space-y-1 text-xs text-slate-300">
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Поток газа</dt>
                    <dd>{fmtNum(selected.ch4_flux_m3_h)} м³/ч</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">H₂S</dt>
                    <dd>{fmtNum(selected.h2s_ppm)} ppm</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Возраст массива</dt>
                    <dd>{AGE_LABEL[selected.age_class]}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Риск нестабильности</dt>
                    <dd>{fmtPercent(selected.instability_proba, 0)}</dd>
                  </div>
                </dl>
              </div>
            ) : (
              <p className="text-xs leading-relaxed text-slate-500">
                Выберите сектор на карте: увидите поток газа, H₂S, возраст массива и
                ML-прогноз нестабильности. Красные сектора требуют усиленной фильтрации —
                именно там балансировщик отключает узлы первыми.
              </p>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
