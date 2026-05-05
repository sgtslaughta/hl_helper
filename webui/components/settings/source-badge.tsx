'use client';

import { Badge } from '@/components/primitives/badge';

interface SourceBadgeProps {
	source: 'runtime' | 'env' | 'file' | 'default';
}

const SOURCE_CONFIG: Record<
	string,
	{ label: string; variant: 'accent' | 'warn' | 'default' | 'dim' }
> = {
	runtime: { label: 'Runtime', variant: 'accent' },
	env: { label: 'Environment', variant: 'warn' },
	file: { label: 'File', variant: 'default' },
	default: { label: 'Default', variant: 'dim' },
};

export function SourceBadge({ source }: SourceBadgeProps) {
	const config = SOURCE_CONFIG[source] || SOURCE_CONFIG.default;
	return (
		<Badge size="sm" variant={config.variant}>
			{config.label}
		</Badge>
	);
}
