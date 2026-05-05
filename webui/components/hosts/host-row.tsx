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
	tags?: string[];
}

interface HostRowProps {
	host: Host;
}

const statusBadgeVariant = {
	healthy: 'ok',
	warning: 'warn',
	critical: 'danger',
} as const;

export function HostRow({ host }: HostRowProps) {
	return (
		<tr className="border-b border-hairline hover:bg-surface-2 transition-colors">
			<td className="px-4 py-3 text-sm">
				<Link href={`/hosts/${host.id}`} className="text-accent hover:underline">
					{host.name}
				</Link>
			</td>
			<td className="px-4 py-3 text-sm text-text-dim">{host.os}</td>
			<td className="px-4 py-3 text-sm text-text-dim">v{host.version}</td>
			<td className="px-4 py-3">
				<Badge variant={statusBadgeVariant[host.status]} size="sm">
					{host.status}
				</Badge>
			</td>
			<td className="px-4 py-3 text-sm text-text-dim">{host.lastSeen || '—'}</td>
		</tr>
	);
}
