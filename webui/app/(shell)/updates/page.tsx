'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Button } from '@/components/primitives/button';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { PolicyPreview } from '@/components/updates/policy-preview';
import { TargetPicker } from '@/components/updates/target-picker';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface Host {
	id: string;
	name: string;
}

interface Policy {
	id: string;
	name: string;
	description?: string;
	rules?: Array<{
		name: string;
		action: string;
	}>;
}

interface Target {
	id: string;
	name: string;
}

export default function UpdatesPage() {
	const canCreate = useCan('task', 'create');
	const [selectedTargets, setSelectedTargets] = useState<Target[]>([]);
	const [selectedPolicy, setSelectedPolicy] = useState<string>('');

	const { data: hosts, isLoading: hostsLoading } = useQuery({
		queryKey: ['hosts'],
		queryFn: () => apiFetch<Host[]>('/v1/hosts'),
	});

	const { data: policies, isLoading: policiesLoading } = useQuery({
		queryKey: ['policies'],
		queryFn: () => apiFetch<Policy[]>('/v1/policies'),
	});

	const planMutation = useMutation({
		mutationFn: async () => {
			return apiFetch('/v1/tasks', {
				method: 'POST',
				body: JSON.stringify({
					targets: selectedTargets.map(t => t.id),
					policy: selectedPolicy,
				}),
			});
		},
	});

	if (hostsLoading || policiesLoading) return <BlueprintSkeleton rows={5} />;
	if (!hosts || !policies) return <EmptyState title="Failed to load updates" />;

	const selectedPolicyObj = policies.find(p => p.id === selectedPolicy);

	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Updates</h1>
				<p className="text-text-dim">Plan and deploy policy updates</p>
			</div>

			{!canCreate && (
				<div className="mb-6 p-4 rounded border border-warn bg-warn bg-opacity-10 text-warn text-sm">
					You do not have permission to create tasks
				</div>
			)}

			<div className="grid grid-cols-3 gap-4">
				<div>
					<h3 className="text-sm font-semibold text-text mb-3">1. Select Targets</h3>
					<TargetPicker
						hosts={hosts}
						groups={[]}
						tags={[]}
						onSelect={(_mode, targets) => setSelectedTargets(targets)}
					/>
				</div>

				<div>
					<h3 className="text-sm font-semibold text-text mb-3">2. Select Policy</h3>
					<div className="rounded border border-hairline bg-surface p-4">
						<select
							value={selectedPolicy}
							onChange={e => setSelectedPolicy(e.target.value)}
							className="w-full px-3 py-2 rounded bg-surface-2 border border-hairline text-text text-sm focus:outline-none focus:border-accent"
						>
							<option value="">Choose a policy...</option>
							{policies.map(p => (
								<option key={p.id} value={p.id}>
									{p.name}
								</option>
							))}
						</select>
					</div>
				</div>

				<div>
					<h3 className="text-sm font-semibold text-text mb-3">3. Review Plan</h3>
					{selectedPolicyObj ? (
						<PolicyPreview policy={selectedPolicyObj} />
					) : (
						<div className="rounded border border-hairline bg-surface p-4 text-text-dim text-sm">
							Select targets and policy to preview
						</div>
					)}
				</div>
			</div>

			<div className="mt-6">
				<Button
					variant="primary"
					onClick={() => planMutation.mutate()}
					disabled={!canCreate || selectedTargets.length === 0 || !selectedPolicy}
					isLoading={planMutation.isPending}
					type="button"
				>
					Plan & Run
				</Button>
			</div>
		</div>
	);
}
