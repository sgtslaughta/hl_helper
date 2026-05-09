'use client';

import Link from 'next/link';
import type { TickerEvent } from '@/lib/ticker-types';
import { resolveLink } from '@/lib/ticker-links';

interface Props {
	event: TickerEvent;
	isNew: boolean;
}

function formatTime(ts: string): string {
	const d = new Date(ts);
	if (Number.isNaN(d.getTime())) return '--:--:--';
	return d.toLocaleTimeString('en-US', {
		hour12: false,
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
	});
}

export function TickerMessage({ event, isNew }: Props) {
	const href = resolveLink(event);
	const body = (
		<span className="inline-flex items-center gap-2 px-3 py-1 whitespace-nowrap text-[10px]">
			{isNew && (
				<span
					className="mc-led mc-led-pulse"
					aria-label="new"
					style={{ color: 'var(--color-warn)', width: 6, height: 6 }}
				/>
			)}
			<span
				className="mc-readout"
				style={{ color: 'var(--color-text-dim)', opacity: 0.65 }}
			>
				{formatTime(event.ts)}
			</span>
			<span
				className="mc-pip"
				style={{
					color: 'var(--color-text-dim)',
					opacity: 0.55,
					borderColor: 'var(--color-text-dim)',
					fontSize: 9,
				}}
			>
				{event.type}
			</span>
			<span style={{ color: 'var(--color-text-dim)', opacity: 0.85 }}>{event.text}</span>
		</span>
	);

	return href ? (
		<Link
			href={href}
			className="hover:text-accent transition-colors"
			data-testid="ticker-message"
		>
			{body}
		</Link>
	) : (
		<span data-testid="ticker-message">{body}</span>
	);
}
