'use client';

import { Badge } from '@/components/primitives/badge';
import { Switch } from '@/components/primitives/switch';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useState } from 'react';
import { CapabilityChip } from './capability-chip';

interface PluginCardProps {
	id: string;
	version: string;
	name: string;
	state: 'disabled' | 'enabled' | 'paused' | 'broken';
	capabilities?: string[];
	onStateChange?: (newState: string) => void;
}

const STATE_VARIANTS: Record<string, 'danger' | 'warn' | 'ok' | 'default'> = {
	disabled: 'danger',
	enabled: 'ok',
	paused: 'warn',
	broken: 'danger',
};

export function PluginCard({
	id,
	version,
	name,
	state,
	capabilities = [],
	onStateChange,
}: PluginCardProps) {
	const [isLoading, setIsLoading] = useState(false);
	const canToggle = useCan('plugin:write', id);

	const handleToggle = async () => {
		if (!canToggle) return;

		setIsLoading(true);
		try {
			const newState = state === 'enabled' ? 'disabled' : 'enabled';
			await apiFetch(`/v1/plugins/${id}`, {
				method: 'PATCH',
				body: JSON.stringify({ state: newState }),
			});
			onStateChange?.(newState);
		} catch (err) {
			console.error('Failed to toggle plugin state:', err);
		} finally {
			setIsLoading(false);
		}
	};

	return (
		<div className="flex flex-col gap-4 rounded border border-hairline bg-surface p-6">
			{/* Header */}
			<div className="flex items-start justify-between">
				<div className="flex-1">
					<h3 className="text-base font-semibold text-text">{name}</h3>
					<p className="text-small text-text-dim">{id}</p>
					<p className="text-small text-text-dim">v{version}</p>
				</div>
				<Badge variant={STATE_VARIANTS[state] || 'default'} size="sm">
					{state.charAt(0).toUpperCase() + state.slice(1)}
				</Badge>
			</div>

			{/* Capabilities */}
			{capabilities.length > 0 && (
				<div className="flex flex-wrap gap-2">
					{capabilities.map(cap => (
						<CapabilityChip key={cap} capability={cap} />
					))}
				</div>
			)}

			{/* Actions */}
			{canToggle && (
				<div className="flex items-center gap-4 pt-2">
					<Switch
						checked={state === 'enabled'}
						onCheckedChange={handleToggle}
						disabled={isLoading}
						label={state === 'enabled' ? 'Enabled' : 'Disabled'}
					/>
				</div>
			)}
		</div>
	);
}
