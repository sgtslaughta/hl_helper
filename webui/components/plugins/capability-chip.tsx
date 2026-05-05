'use client';

import { Badge } from '@/components/primitives/badge';
import { Archive, Globe, Lock, Zap } from 'lucide-react';

interface CapabilityChipProps {
	capability: string;
}

const CAPABILITY_ICONS: Record<string, React.ReactNode> = {
	'egress.http': <Globe className="h-3 w-3" />,
	'egress.tcp': <Globe className="h-3 w-3" />,
	'secrets.read': <Lock className="h-3 w-3" />,
	'hooks.update.pre': <Zap className="h-3 w-3" />,
	'hooks.update.post': <Zap className="h-3 w-3" />,
	'hooks.task.created': <Zap className="h-3 w-3" />,
	'hooks.notification.route': <Zap className="h-3 w-3" />,
	'storage.local': <Archive className="h-3 w-3" />,
};

const CAPABILITY_LABELS: Record<string, string> = {
	'egress.http': 'HTTP',
	'egress.tcp': 'TCP',
	'secrets.read': 'Secrets',
	'hooks.update.pre': 'Pre-Update',
	'hooks.update.post': 'Post-Update',
	'hooks.task.created': 'Task Hook',
	'hooks.notification.route': 'Notify',
	'storage.local': 'Storage',
};

export function CapabilityChip({ capability }: CapabilityChipProps) {
	const icon = CAPABILITY_ICONS[capability];
	const label = CAPABILITY_LABELS[capability] || capability;

	return (
		<Badge size="sm" variant="dim" className="flex items-center gap-1">
			{icon && <span>{icon}</span>}
			<span>{label}</span>
		</Badge>
	);
}
