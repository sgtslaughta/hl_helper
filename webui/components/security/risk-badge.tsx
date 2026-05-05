'use client';

type RiskLevel = 'low' | 'medium' | 'high';

interface RiskBadgeProps {
	level: RiskLevel;
	description?: string;
}

export function RiskBadge({ level, description }: RiskBadgeProps) {
	const colors: Record<RiskLevel, { bg: string; text: string }> = {
		low: { bg: 'bg-ok', text: 'text-canvas' },
		medium: { bg: 'bg-warn', text: 'text-canvas' },
		high: { bg: 'bg-danger', text: 'text-canvas' },
	};

	const c = colors[level];

	return (
		<div
			className={`inline-flex items-center rounded px-2 py-1 text-small font-semibold ${c.bg} ${c.text}`}
			title={description}
		>
			{level.charAt(0).toUpperCase() + level.slice(1)}
		</div>
	);
}
