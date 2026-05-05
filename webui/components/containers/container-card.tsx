'use client';

import { Badge } from '@/components/primitives/badge';
import Link from 'next/link';

interface Container {
	id: string;
	name: string;
	image: string;
	host: string;
	status: 'running' | 'stopped' | 'paused';
	uptime?: string;
}

interface ContainerCardProps {
	container: Container;
}

const statusBadgeVariant = {
	running: 'ok',
	stopped: 'dim',
	paused: 'warn',
} as const;

export function ContainerCard({ container }: ContainerCardProps) {
	return (
		<Link href={`/containers/${container.host}/${container.id}`}>
			<div className="rounded border border-hairline bg-surface p-4 hover:bg-surface-2 cursor-pointer transition-colors">
				<div className="flex items-start justify-between mb-2">
					<h3 className="text-sm font-semibold text-text truncate">{container.name}</h3>
					<Badge variant={statusBadgeVariant[container.status]} size="sm">
						{container.status}
					</Badge>
				</div>
				<p className="text-xs text-text-dim mb-3 truncate">{container.image}</p>
				<div className="flex items-center justify-between text-xs">
					<span className="text-text-dim">{container.host}</span>
					{container.uptime && <span className="text-text-dim">{container.uptime}</span>}
				</div>
			</div>
		</Link>
	);
}
