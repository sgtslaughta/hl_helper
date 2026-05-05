'use client';

interface CapabilityChipProps {
	permission: string;
	tooltip?: string;
}

export function CapabilityChip({ permission, tooltip }: CapabilityChipProps) {
	const [resource, action] = permission.split(':');
	return (
		<div
			className="inline-flex items-center rounded-full bg-surface-2 px-3 py-1 text-tiny font-semibold text-text"
			title={tooltip || permission}
		>
			<span className="text-accent">{resource}</span>
			<span className="mx-1">:</span>
			<span>{action || '*'}</span>
		</div>
	);
}
