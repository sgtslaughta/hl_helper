import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDensity, DENSITIES } from '@/lib/mission-control/density';

describe('useDensity', () => {
  beforeEach(() => localStorage.clear());

  it('defaults to balanced', () => {
    const { result } = renderHook(() => useDensity());
    expect(result.current.density).toBe('balanced');
  });

  it('cycles through Lean → Balanced → Rich → Lean', () => {
    const { result } = renderHook(() => useDensity());
    act(() => result.current.cycle());
    expect(result.current.density).toBe('rich');
    act(() => result.current.cycle());
    expect(result.current.density).toBe('lean');
    act(() => result.current.cycle());
    expect(result.current.density).toBe('balanced');
  });

  it('persists across hook remounts via localStorage', () => {
    const first = renderHook(() => useDensity());
    act(() => first.result.current.set('rich'));
    first.unmount();
    const second = renderHook(() => useDensity());
    expect(second.result.current.density).toBe('rich');
  });

  it('exports DENSITIES constant', () => {
    expect(DENSITIES).toEqual(['lean', 'balanced', 'rich']);
  });
});
