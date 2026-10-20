import { useEffect, useState } from 'react';

/**
 * Реактивный matchMedia. Нужен прежде всего для Recharts: размеры тиков,
 * осей и отступов задаются в px через props и не масштабляются rem-типографикой.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    typeof window === 'undefined' ? false : window.matchMedia(query).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent): void => setMatches(event.matches);
    setMatches(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/** Телефонная ширина (< 640px — тот же порог, что Tailwind sm). */
export function useIsPhone(): boolean {
  return useMediaQuery('(max-width: 639px)');
}
