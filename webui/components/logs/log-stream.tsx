'use client';

import { getWSClient } from '@/lib/ws-client';
import { useQueryClient } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

interface LogEntry {
	id: string;
	timestamp: string;
	message: string;
	level: 'debug' | 'info' | 'warn' | 'error';
}

interface LogStreamProps {
	wsChannel: string;
}

export function LogStream({ wsChannel }: LogStreamProps) {
	const [logs, _setLogs] = useState<LogEntry[]>([]);
	const [searchTerm, setSearchTerm] = useState('');
	const [autoScroll, setAutoScroll] = useState(true);
	const queryClient = useQueryClient();
	const parentRef = useRef<HTMLDivElement>(null);
	const _wsRef = useRef<WebSocket | null>(null);
	void _wsRef;

	useEffect(() => {
		const wsClient = getWSClient(queryClient);
		wsClient.subscribe(wsChannel);

		return () => {
			wsClient.unsubscribe(wsChannel);
		};
	}, [wsChannel, queryClient]);

	const filteredLogs = searchTerm
		? logs.filter(log => log.message.toLowerCase().includes(searchTerm.toLowerCase()))
		: logs;

	const virtualizer = useVirtualizer({
		count: filteredLogs.length,
		getScrollElement: () => parentRef.current,
		estimateSize: () => 32,
		overscan: 10,
	});

	useEffect(() => {
		if (autoScroll && filteredLogs.length > 0) {
			virtualizer.measureElement(
				typeof window !== 'undefined' ? document.createElement('div') : null,
			);
			const lastIndex = filteredLogs.length - 1;
			virtualizer.scrollToIndex(lastIndex, { align: 'end', behavior: 'auto' });
		}
	}, [filteredLogs.length, autoScroll, virtualizer]);

	const getLevelColor = (level: string) => {
		switch (level) {
			case 'error':
				return 'text-danger';
			case 'warn':
				return 'text-warn';
			case 'info':
				return 'text-accent';
			default:
				return 'text-text-dim';
		}
	};

	const virtualItems = virtualizer.getVirtualItems();

	return (
		<div className="flex h-full flex-col gap-2">
			<div className="flex items-center gap-2 border-b border-hairline px-3 py-2">
				<Search size={14} className="text-text-dim" />
				<input
					type="text"
					placeholder="Search logs..."
					value={searchTerm}
					onChange={e => setSearchTerm(e.target.value)}
					className="flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text-dim"
				/>
				<label className="flex items-center gap-1 text-xs text-text-dim">
					<input
						type="checkbox"
						checked={autoScroll}
						onChange={e => setAutoScroll(e.target.checked)}
						className="rounded"
					/>
					<span>Auto-scroll</span>
				</label>
			</div>

			<div
				ref={parentRef}
				className="flex-1 overflow-auto font-mono text-xs"
				style={{
					contain: 'strict',
				}}
			>
				<div
					style={{
						height: `${virtualizer.getTotalSize()}px`,
						width: '100%',
						position: 'relative',
					}}
				>
					{virtualItems.map(virtualItem => {
						const log = filteredLogs[virtualItem.index];
						return (
							<div
								key={log.id}
								data-index={virtualItem.index}
								className="absolute left-0 right-0 flex gap-2 px-3 py-1"
								style={{
									transform: `translateY(${virtualItem.start}px)`,
								}}
							>
								<span className="text-text-dim w-40 shrink-0">[{log.timestamp}]</span>
								<span className={`w-12 shrink-0 ${getLevelColor(log.level)}`}>
									{log.level.toUpperCase()}
								</span>
								<span className="flex-1 text-text">{log.message}</span>
							</div>
						);
					})}
				</div>
			</div>
		</div>
	);
}
