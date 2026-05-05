'use client';

import { Plus, X } from 'lucide-react';
import { useState } from 'react';
import { TerminalPane } from './terminal-pane';

interface Tab {
	id: string;
	hostId: string;
	label: string;
}

export function TerminalTabs() {
	const [tabs, setTabs] = useState<Tab[]>([]);
	const [activeTabId, setActiveTabId] = useState<string | null>(null);

	const addTab = (hostId: string) => {
		const id = `tab-${Date.now()}`;
		const newTab: Tab = { id, hostId, label: `Terminal: ${hostId}` };
		setTabs(prev => [...prev, newTab]);
		setActiveTabId(id);
	};

	const closeTab = (id: string) => {
		setTabs(prev => prev.filter(t => t.id !== id));
		if (activeTabId === id) {
			setActiveTabId(tabs[0]?.id || null);
		}
	};

	const activeTab = tabs.find(t => t.id === activeTabId);

	return (
		<div className="flex h-full flex-col">
			<div className="flex border-b border-hairline">
				{tabs.map(tab => (
					<button
						key={tab.id}
						type="button"
						onClick={() => setActiveTabId(tab.id)}
						className={`flex items-center gap-2 border-r border-hairline px-3 py-2 text-sm ${
							activeTabId === tab.id
								? 'bg-surface text-text'
								: 'bg-surface-2 text-text-dim hover:text-text'
						}`}
					>
						<span>{tab.label}</span>
						<button
							type="button"
							onClick={e => {
								e.stopPropagation();
								closeTab(tab.id);
							}}
							className="rounded hover:bg-surface-2 p-0.5"
						>
							<X size={14} />
						</button>
					</button>
				))}
				<button
					type="button"
					onClick={() => addTab('new-host')}
					className="flex items-center gap-1 border-r border-hairline bg-surface px-3 py-2 text-sm text-text-dim hover:text-text"
				>
					<Plus size={14} />
					<span>Add</span>
				</button>
			</div>
			{activeTab ? (
				<div className="flex-1 overflow-hidden">
					<TerminalPane hostId={activeTab.hostId} />
				</div>
			) : (
				<div className="flex flex-1 items-center justify-center text-text-dim">
					<span>No terminals open</span>
				</div>
			)}
		</div>
	);
}
