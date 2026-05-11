'use client';

import { useEffect, useRef, useState } from 'react';

interface ActivitySplitProps {
	top: React.ReactNode;
	bottom: React.ReactNode;
	initialRatio?: number;
}

const RATIO_KEY = 'activity.split.ratio';
const DEFAULT_RATIO = 0.55;

export function ActivitySplit({ top, bottom, initialRatio = DEFAULT_RATIO }: ActivitySplitProps) {
	const [ratio, setRatio] = useState(initialRatio);
	const [isDragging, setIsDragging] = useState(false);
	const containerRef = useRef<HTMLDivElement>(null);

	// Load persisted ratio on mount
	useEffect(() => {
		if (typeof window !== 'undefined') {
			const stored = localStorage.getItem(RATIO_KEY);
			if (stored) {
				const n = Number.parseFloat(stored);
				if (Number.isFinite(n) && n > 0.2 && n < 0.8) {
					setRatio(n);
				}
			}
		}
	}, []);

	// Drag handlers
	useEffect(() => {
		if (!isDragging || !containerRef.current) return;

		const onMouseMove = (e: MouseEvent) => {
			const container = containerRef.current;
			if (!container) return;

			const rect = container.getBoundingClientRect();
			const newRatio = Math.max(0.2, Math.min(0.8, (e.clientY - rect.top) / rect.height));
			setRatio(newRatio);
		};

		const onMouseUp = () => {
			setIsDragging(false);
			document.body.style.userSelect = '';
			try {
				localStorage.setItem(RATIO_KEY, String(ratio));
			} catch {}
		};

		document.addEventListener('mousemove', onMouseMove);
		document.addEventListener('mouseup', onMouseUp);

		return () => {
			document.removeEventListener('mousemove', onMouseMove);
			document.removeEventListener('mouseup', onMouseUp);
		};
	}, [isDragging, ratio]);

	const topHeight = `${ratio * 100}%`;
	const bottomHeight = `${(1 - ratio) * 100}%`;

	return (
		<div
			ref={containerRef}
			className="flex flex-col h-full gap-0 overflow-hidden"
		>
			{/* Top pane */}
			<div style={{ height: topHeight }} className="overflow-hidden flex flex-col bg-surface">
				{top}
			</div>

			{/* Drag handle */}
			<button
				type="button"
				onMouseDown={() => {
					setIsDragging(true);
					document.body.style.userSelect = 'none';
				}}
				className="h-1 bg-surface-alt hover:bg-accent/30 cursor-row-resize transition-colors flex-shrink-0"
				aria-label="Drag to resize panes"
			/>

			{/* Bottom pane */}
			<div style={{ height: bottomHeight }} className="overflow-hidden flex flex-col bg-surface-2">
				{bottom}
			</div>
		</div>
	);
}
