import { useEffect, useState, useCallback } from 'react';

export const DENSITIES = ['lean', 'balanced', 'rich'] as const;
export type Density = (typeof DENSITIES)[number];

const STORAGE_KEY = 'mc.density';

export function useDensity() {
  const [density, setDensity] = useState<Density>('balanced');

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Density | null;
    if (stored && DENSITIES.includes(stored)) setDensity(stored);
  }, []);

  const set = useCallback((d: Density) => {
    setDensity(d);
    localStorage.setItem(STORAGE_KEY, d);
  }, []);

  const cycle = useCallback(() => {
    setDensity(prev => {
      const i = DENSITIES.indexOf(prev);
      const next = DENSITIES[(i + 1) % DENSITIES.length];
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { density, set, cycle };
}
