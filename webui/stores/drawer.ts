'use client';

import { create } from 'zustand';

export type DrawerTab = 'terminals' | 'logs';

interface DrawerState {
	isOpen: boolean;
	height: number;
	activeTab: DrawerTab;
	terminalHost: string | null;
	open: (tab: DrawerTab, hostId?: string) => void;
	close: () => void;
	setHeight: (height: number) => void;
	setActiveTab: (tab: DrawerTab) => void;
}

export const useDrawerStore = create<DrawerState>(set => ({
	isOpen: false,
	height: 240,
	activeTab: 'terminals',
	terminalHost: null,
	open: (tab, hostId) => set({ isOpen: true, activeTab: tab, terminalHost: hostId || null }),
	close: () => set({ isOpen: false }),
	setHeight: (height: number) => set({ height: Math.max(100, Math.min(height, 800)) }),
	setActiveTab: (tab: DrawerTab) => set({ activeTab: tab }),
}));
