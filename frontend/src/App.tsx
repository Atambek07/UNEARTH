import { Component, type ErrorInfo, type ReactNode } from 'react';
import { DashboardLayout } from './components/DashboardLayout';

interface BoundaryState {
  error: Error | null;
}

/** Простой ErrorBoundary: вместо белого экрана — читаемое сообщение. */
class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('UNEARTH UI error:', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-slate-900 p-6 text-slate-100">
          <div className="max-w-lg rounded-xl border border-red-500/40 bg-red-500/10 p-6">
            <h1 className="mb-2 text-lg font-semibold text-red-300">Дашборд упал</h1>
            <p className="mb-3 text-sm text-slate-300">
              Обновите страницу. Если ошибка повторяется — проверьте консоль браузера.
            </p>
            <pre className="overflow-x-auto rounded bg-slate-950/70 p-3 text-xs text-red-200">
              {this.state.error.message}
            </pre>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App(): JSX.Element {
  return (
    <ErrorBoundary>
      <DashboardLayout />
    </ErrorBoundary>
  );
}
