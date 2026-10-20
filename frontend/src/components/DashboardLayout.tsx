import { useEffect, useState } from 'react';
import { Loader2, Menu, Play, Recycle, SlidersHorizontal, Wifi, WifiOff } from 'lucide-react';
import { useSimulation } from '../store/simulationStore';
import { Sidebar } from './Sidebar';
import { TopCards } from './TopCards';
import { ForecastChart } from './ForecastChart';
import { FinanceChart } from './FinanceChart';
import { AllocationPanel } from './AllocationPanel';
import { PlanPanel } from './PlanPanel';
import { CarbonPanel } from './CarbonPanel';
import { ScenarioPanel } from './ScenarioPanel';
import { SectorMap } from './SectorMap';
import { MaintenancePanel } from './MaintenancePanel';

/** StrictMode монтирует эффекты дважды — первый прогон симуляции делаем один. */
let bootRan = false;

export function DashboardLayout(): JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const apiOnline = useSimulation((s) => s.apiOnline);
  const errors = useSimulation((s) => s.errors);
  const running = useSimulation((s) => s.running);
  const checkHealth = useSimulation((s) => s.checkHealth);
  const run = useSimulation((s) => s.run);

  useEffect(() => {
    void checkHealth();
    if (!bootRan) {
      bootRan = true;
      void run();
    }
  }, [checkHealth, run]);

  /* Мобильное меню: блокируем фон и закрываем по Escape. */
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [menuOpen]);

  const failedSlices = Object.entries(errors)
    .filter(([, message]) => Boolean(message))
    .map(([key]) => key);

  return (
    <div className="flex min-h-dvh bg-slate-900 text-slate-100">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />

      {menuOpen ? (
        <button
          type="button"
          aria-label="Закрыть меню"
          onClick={() => setMenuOpen(false)}
          className="fixed inset-0 z-30 bg-slate-950/70 backdrop-blur-sm lg:hidden"
        />
      ) : null}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-900/95 backdrop-blur">
          <div className="mx-auto flex w-full max-w-[1700px] items-center gap-2 px-3 pt-[calc(0.625rem+env(safe-area-inset-top))] pb-2.5 sm:gap-3 sm:px-4 lg:px-6">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Открыть параметры"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-700 text-slate-300 transition hover:border-slate-500 hover:text-slate-100 active:bg-slate-800 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>

            <Recycle className="hidden h-7 w-7 shrink-0 text-emerald-400 sm:block" />

            <div className="min-w-0 flex-1">
              <h1 className="truncate text-sm font-bold leading-tight sm:text-lg">
                UNEARTH — Smart LFG Grid
              </h1>
              <p className="hidden truncate text-xs text-slate-400 sm:block">
                Бишкекский полигон · 20 млн т ТБО · off-grid ИИ/майнинг
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-1.5 text-[11px] text-slate-400 sm:gap-2 sm:text-xs">
              {apiOnline === false ? (
                <WifiOff className="h-4 w-4 text-red-400" />
              ) : (
                <Wifi className={`h-4 w-4 ${apiOnline ? 'text-emerald-400' : 'text-slate-500'}`} />
              )}
              <span className="hidden sm:inline">
                {apiOnline === false ? 'API недоступен' : apiOnline ? 'на связи' : '…'}
              </span>
            </div>
          </div>
        </header>

        <div className="mx-auto w-full max-w-[1700px] flex-1 space-y-4 px-3 pt-4 pb-28 sm:space-y-6 sm:px-4 lg:px-6 lg:pt-6 lg:pb-6">
          {failedSlices.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs leading-relaxed text-amber-200 sm:px-4 sm:py-3 sm:text-sm">
              Модули без ответа: <b>{failedSlices.join(', ')}</b>. Проверьте, что backend запущен
              (из папки backend/: <code>uvicorn app.main:app --port 8000</code>) — см. README.
            </div>
          )}

          <TopCards />

          <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-2">
            <ForecastChart />
            <FinanceChart />
          </div>

          <AllocationPanel />

          <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-2">
            <PlanPanel />
            <CarbonPanel />
          </div>

          <ScenarioPanel />
          <SectorMap />
          <MaintenancePanel />

          <footer className="pb-2 text-center text-[11px] leading-relaxed text-slate-500 sm:text-[10px]">
            UNEARTH MVP · LandGEM (EPA) + ML-сезонность + Smart Grid · симуляционные данные,
            не инвестиционная рекомендация
          </footer>
        </div>

        {/* Мобильная панель действий: всегда под рукой */}
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-800 bg-slate-950/95 px-3 pt-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] backdrop-blur lg:hidden">
          <div className="flex items-stretch gap-2">
            <button
              type="button"
              onClick={() => void run()}
              disabled={running}
              className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 text-sm font-semibold text-slate-950 transition active:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {running ? 'Симуляция…' : 'Запустить симуляцию'}
            </button>
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-slate-700 px-3 text-xs font-medium text-slate-300 active:bg-slate-800"
            >
              <SlidersHorizontal className="h-4 w-4" />
              Параметры
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
