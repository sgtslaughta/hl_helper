import { create } from 'zustand';

export interface PaletteStore {
	open: boolean;
	setOpen: (v: boolean) => void;
	toggle: () => void;
}

export const usePaletteStore = create<PaletteStore>(set => ({
	open: false,
	setOpen: v => set({ open: v }),
	toggle: () => set(s => ({ open: !s.open })),
}));
