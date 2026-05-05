import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DocsModeStore {
	mode: 'beginner' | 'advanced';
	setMode: (mode: 'beginner' | 'advanced') => void;
}

export const useDocsModeStore = create<DocsModeStore>()(
	persist(
		set => ({
			mode: 'beginner',
			setMode: mode => set({ mode }),
		}),
		{
			name: 'docs-mode-store',
		},
	),
);
