import { create } from 'zustand';

export interface SidebarStore {
	collapsed: boolean;
	toggle: () => void;
}

export const useSidebarStore = create<SidebarStore>(set => ({
	collapsed: false,
	toggle: () => set(state => ({ collapsed: !state.collapsed })),
}));
