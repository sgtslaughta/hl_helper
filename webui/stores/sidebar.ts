import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface SidebarStore {
	collapsed: boolean;
	hasHydrated: boolean;
	toggle: () => void;
	setCollapsed: (v: boolean) => void;
	_setHasHydrated: (v: boolean) => void;
}

export const useSidebarStore = create<SidebarStore>()(
	persist(
		set => ({
			collapsed: false,
			hasHydrated: false,
			toggle: () => set(state => ({ collapsed: !state.collapsed })),
			setCollapsed: v => set({ collapsed: v }),
			_setHasHydrated: v => set({ hasHydrated: v }),
		}),
		{
			name: 'sidebar-store',
			partialize: state => ({ collapsed: state.collapsed }),
			onRehydrateStorage: () => state => {
				state?._setHasHydrated(true);
			},
		},
	),
);
