'use client';

import { Badge } from '@/components/primitives/badge';
import Link from 'next/link';

interface Host {
	id: string;
	name: string;
	status: 'healthy' | 'warning' | 'critical';
	os: string;
	version: string;
	lastSeen?: string;
}

interface HostCardProps {
	host: Host;
}

const statusBadgeVariant = {
	healthy: 'ok',
	warning: 'warn',
	critical: 'danger',
} as const;

export function HostCard({ host }: HostCardProps) {
	return (
		<Link href={`/hosts/${host.id}`}>
			<div className="rounded border border-hairline bg-surface p-4 hover:bg-surface-2 cursor-pointer transition-colors">
				<div className="flex items-start justify-between mb-2">
					<h3 className="text-sm font-semibold text-text truncate">{host.name}</h3>
					<Badge variant={statusBadgeVariant[host.status]} size="sm">
						{host.status}
					</Badge>
				</div>
				<p className="text-xs text-text-dim mb-3">{host.os}</p>
				<div className="flex items-center justify-between text-xs">
					<span className="text-text-dim">v{host.version}</span>
					{host.lastSeen && <span className="text-text-dim">{host.lastSeen}</span>}
				</div>
			</div>
		</Link>
	);
}
