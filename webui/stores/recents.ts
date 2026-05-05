import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface RecentItem {
	id: string;
	label: string;
	index: string;
	timestamp: number;
}

interface RecentsStore {
	items: RecentItem[];
	add: (item: Omit<RecentItem, 'timestamp'>) => void;
	clear: () => void;
}

const MAX_RECENTS = 20;

export const useRecentsStore = create<RecentsStore>()(
	persist(
		set => ({
			items: [],
			add: item =>
				set(state => {
					const filtered = state.items.filter(i => !(i.id === item.id && i.index === item.index));
					const newItems = [{ ...item, timestamp: Date.now() }, ...filtered].slice(0, MAX_RECENTS);
					return { items: newItems };
				}),
			clear: () => set({ items: [] }),
		}),
		{
			name: 'recents-storage',
		},
	),
);
