'use client';

import { LogStream } from '@/components/logs/log-stream';
import { TerminalTabs } from '@/components/terminal/terminal-tabs';
import { useDrawerStore } from '@/stores/drawer';
import { ChevronUp, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useHotkeys } from 'react-hotkeys-hook';

export function BottomDrawer() {
	const { isOpen, close, height, setHeight, activeTab, setActiveTab } = useDrawerStore();
	const [isDragging, setIsDragging] = useState(false);
	const drawerRef = useRef<HTMLDivElement>(null);

	// Hotkey: cmd+` to toggle drawer
	useHotkeys(
		'cmd+`,ctrl+`',
		() => {
			if (isOpen) {
				close();
			} else {
				useDrawerStore.setState({ isOpen: true });
			}
		},
		{ preventDefault: true },
	);

	useEffect(() => {
		if (!isDragging) return;

		const handleMouseMove = (e: MouseEvent) => {
			if (drawerRef.current) {
				const newHeight = window.innerHeight - e.clientY;
				setHeight(newHeight);
			}
		};

		const handleMouseUp = () => {
			setIsDragging(false);
		};

		document.addEventListener('mousemove', handleMouseMove);
		document.addEventListener('mouseup', handleMouseUp);

		return () => {
			document.removeEventListener('mousemove', handleMouseMove);
			document.removeEventListener('mouseup', handleMouseUp);
		};
	}, [isDragging, setHeight]);

	if (!isOpen) return null;

	return (
		<div
			ref={drawerRef}
			className="flex flex-col border-t border-hairline bg-canvas"
			style={{ height: `${height}px` }}
		>
			{/* Drag handle */}
			<div
				onMouseDown={() => setIsDragging(true)}
				className="flex cursor-row-resize items-center justify-between border-b border-hairline bg-surface px-4 py-2 hover:bg-surface-2"
			>
				<div className="flex items-center gap-2">
					<ChevronUp size={16} className="text-text-dim" />
					<span className="text-xs font-semibold text-text">
						{activeTab === 'terminals' ? 'Terminals' : 'Logs'}
					</span>
				</div>
				<button
					type="button"
					onClick={() => close()}
					className="rounded p-1 hover:bg-surface-2"
					title="Close drawer"
				>
					<X size={16} className="text-text-dim" />
				</button>
			</div>

			{/* Tab buttons */}
			<div className="flex border-b border-hairline bg-surface">
				<button
					type="button"
					onClick={() => setActiveTab('terminals')}
					className={`flex-1 px-4 py-2 text-sm font-medium ${
						activeTab === 'terminals'
							? 'border-b-2 border-accent text-text'
							: 'text-text-dim hover:text-text'
					}`}
				>
					Terminals
				</button>
				<button
					type="button"
					onClick={() => setActiveTab('logs')}
					className={`flex-1 px-4 py-2 text-sm font-medium ${
						activeTab === 'logs'
							? 'border-b-2 border-accent text-text'
							: 'text-text-dim hover:text-text'
					}`}
				>
					Logs
				</button>
			</div>

			{/* Content */}
			<div className="flex-1 overflow-hidden">
				{activeTab === 'terminals' ? <TerminalTabs /> : <LogStream wsChannel="logs.stream" />}
			</div>
		</div>
	);
}
