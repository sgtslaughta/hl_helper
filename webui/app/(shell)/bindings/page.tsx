'use client';

export const dynamic = 'force-dynamic';

import { EffectivePermsInspector } from '@/components/bindings/effective-perms-inspector';
import { EmptyState } from '@/components/empty-states/empty-state';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useQuery } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { useState } from 'react';

interface Binding {
	id: string;
	principal_type: string;
	principal_id: string;
	role_id: string;
	scope_kind: string;
	scope_value: Record<string, unknown>;
	created_at: string;
}

export default function BindingsPage() {
	const canRead = useCan('bindings:read');
	const [inspectorOpen, setInspectorOpen] = useState(false);

	const { data, isLoading } = useQuery<{ bindings: Binding[] }>({
		queryKey: ['bindings'],
		queryFn: async () => {
			return await apiFetch('/v1/bindings');
		},
		enabled: canRead,
	});

	if (!canRead) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view bindings"
				icon="🔒"
			/>
		);
	}

	const bindings = data?.bindings || [];

	return (
		<div className="flex flex-col gap-6 p-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-h1 text-text">Bindings</h1>
					<p className="mt-2 text-text-dim">Role assignments and effective permissions</p>
				</div>
				<button
					type="button"
					onClick={() => setInspectorOpen(true)}
					className="rounded border border-accent px-4 py-2 font-semibold text-accent hover:bg-accent/10"
				>
					Inspect Permissions
				</button>
			</div>

			<EffectivePermsInspector isOpen={inspectorOpen} onClose={() => setInspectorOpen(false)} />

			{isLoading ? (
				<div className="text-center text-text-dim">Loading bindings...</div>
			) : bindings.length === 0 ? (
				<EmptyState
					title="No bindings"
					description="No role bindings configured"
					icon={<KeyRound className="h-8 w-8 text-text-dim" />}
				/>
			) : (
				<div className="overflow-x-auto">
					<table className="w-full text-small">
						<thead>
							<tr className="border-b border-hairline text-text-dim">
								<th className="px-4 py-2 text-left">Principal</th>
								<th className="px-4 py-2 text-left">Type</th>
								<th className="px-4 py-2 text-left">Role ID</th>
								<th className="px-4 py-2 text-left">Scope</th>
							</tr>
						</thead>
						<tbody>
							{bindings.map(binding => (
								<tr key={binding.id} className="border-b border-hairline hover:bg-surface-2">
									<td className="px-4 py-2 font-mono text-accent">{binding.principal_id}</td>
									<td className="px-4 py-2 text-text-dim">{binding.principal_type}</td>
									<td className="px-4 py-2 text-text-dim">{binding.role_id}</td>
									<td className="px-4 py-2">
										<span className="rounded bg-surface px-2 py-1 text-tiny">
											{binding.scope_kind}
										</span>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</div>
	);
}
