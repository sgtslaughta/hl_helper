'use client';

import { resolveLink } from '@/lib/ticker-links';
import type { TickerEvent } from '@/lib/ticker-types';
import Link from 'next/link';

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
	// Group-hover bumps each child's opacity to 1 so the entire message
	// pops on hover. Filter brightness adds a second-stage glow on top.
	const body = (
		<span className="group inline-flex items-center gap-2 px-3 py-1 whitespace-nowrap text-[10px] transition-[filter] duration-150 hover:brightness-150">
			{isNew && (
				<span
					className="mc-led mc-led-pulse"
					aria-label="new"
					style={{ color: 'var(--color-warn)', width: 6, height: 6 }}
				/>
			)}
			<span
				className="mc-readout transition-opacity duration-150 group-hover:opacity-100"
				style={{ color: 'var(--color-text-dim)', opacity: 0.65 }}
			>
				{formatTime(event.ts)}
			</span>
			<span
				className="mc-pip transition-opacity duration-150 group-hover:opacity-100"
				style={{
					color: 'var(--color-text-dim)',
					opacity: 0.55,
					borderColor: 'var(--color-text-dim)',
					fontSize: 9,
				}}
			>
				{event.type}
			</span>
			<span
				className="transition-opacity duration-150 group-hover:opacity-100"
				style={{ color: 'var(--color-text-dim)', opacity: 0.85 }}
			>
				{event.text}
			</span>
		</span>
	);

	return href ? (
		<Link href={href} className="transition-colors hover:text-accent" data-testid="ticker-message">
			{body}
		</Link>
	) : (
		<span data-testid="ticker-message">{body}</span>
	);
}
