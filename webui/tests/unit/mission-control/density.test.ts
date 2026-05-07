import { DENSITIES, useDensity } from '@/lib/mission-control/density';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

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
