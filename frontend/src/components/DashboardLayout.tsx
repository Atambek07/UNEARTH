import { useEffect } from 'react';
import { Recycle, Wifi, WifiOff } from 'lucide-react';
import { useSimulation } from '../store/simulationStore';
import { Sidebar } from './Sidebar';
import { TopCards } from './TopCards';
import { ForecastChart } from './ForecastChart';
import { FinanceChart } from './FinanceChart';
import { AllocationPanel } from './AllocationPanel';
import { SectorMap } from './SectorMap';
import { MaintenancePanel } from './MaintenancePanel';

/** StrictMode монтирует эффекты дважды — первый прогон симуляции делаем один. */
let bootRan = false;

export function DashboardLayout(): JSX.Element {
  const apiOnline = useSimulation((s) => s.apiOnline);
  const errors = useSimulation((s) => s.errors);
  const checkHealth = useSimulation((s) => s.checkHealth);
  const run = useSimulation((s) => s.run);

  useEffect(() => {
    void checkHealth();
    if (!bootRan) {
      bootRan = true;
      void run();
    }
  }, [checkHealth, run]);

  const failedSlices = Object.entries(errors)
    .filter(([, message]) => Boolean(message))
    .map(([key]) => key);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-900 text-slate-100">
      <Sidebar />

      <main className="flex-1 overflow-y-auto">
        <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/90 px-6 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <Recycle className="h-7 w-7 text-emerald-400" />
            <div>
              <h1 className="text-lg font-bold leading-tight">
                UNEARTH — Smart LFG-to-Energy Grid
              </h1>
              <p className="text-xs text-slate-400">
                Бишкекский санитарный полигон · 20 млн т ТБО · off-grid ИИ/майнинг кластер
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {apiOnline === false ? (
              <WifiOff className="h-4 w-4 text-red-400" />
            ) : (
              <Wifi className={`h-4 w-4 ${apiOnline ? 'text-emerald-400' : 'text-slate-500'}`} />
            )}
            <span>
              API {apiOnline === false ? 'недоступен' : apiOnline ? 'на связи' : '…'}
            </span>
          </div>
        </header>

        <div className="space-y-6 p-6">
          {failedSlices.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              Модули без ответа: <b>{failedSlices.join(', ')}</b>. Проверьте, что backend запущен
              (из папки backend/: <code>uvicorn app.main:app --port 8000</code>) — см. README.
            </div>
          )}

          <TopCards />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ForecastChart />
            <FinanceChart />
          </div>

          <AllocationPanel />
          <SectorMap />
          <MaintenancePanel />

          <footer className="pb-4 text-center text-xs text-slate-600">
            UNEARTH MVP · LandGEM (EPA) + ML-сезонность + Smart Grid · симуляционные данные,
            не инвестиционная рекомендация
          </footer>
        </div>
      </main>
    </div>
  );
}
