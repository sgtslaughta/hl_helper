'use client';

import { AdvisoryCard } from '@/components/advisories/advisory-card';
import { EmptyState } from '@/components/empty-states/empty-state';
import { Select } from '@/components/primitives/select';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';

interface Advisory {
	id: string;
	severity: string;
	title: string;
	summary: string;
	affected_hosts: number;
	patch_url: string | null;
}

export default function AdvisoriesPage() {
	const [severityFilter, setSeverityFilter] = useState<string>('all');
	const canRead = useCan('advisories:read');

	const { data, isLoading } = useQuery<{ advisories: Advisory[] }>({
		queryKey: ['advisories', { severityFilter }],
		queryFn: async () => {
			return await apiFetch('/v1/advisories');
		},
		enabled: canRead,
	});

	if (!canRead) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view advisories"
				icon="🔒"
			/>
		);
	}

	const advisories = data?.advisories || [];

	const filtered = advisories.filter(a => {
		if (severityFilter !== 'all' && a.severity !== severityFilter) {
			return false;
		}
		return true;
	});

	return (
		<div className="flex flex-col gap-6 p-6">
			<div>
				<h1 className="text-h1 text-text">Advisories</h1>
				<p className="mt-2 text-text-dim">Security advisories and patches</p>
			</div>

			<Select
				value={severityFilter}
				onValueChange={setSeverityFilter}
				options={[
					{ value: 'all', label: 'All Severities' },
					{ value: 'critical', label: 'Critical' },
					{ value: 'high', label: 'High' },
					{ value: 'medium', label: 'Medium' },
					{ value: 'low', label: 'Low' },
				]}
			/>

			{isLoading ? (
				<div className="text-center text-text-dim">Loading advisories...</div>
			) : filtered.length === 0 ? (
				<EmptyState
					title="No advisories"
					description="No advisories match your filters"
					icon={<AlertTriangle className="h-8 w-8 text-text-dim" />}
				/>
			) : (
				<div className="space-y-3">
					{filtered.map(a => (
						<AdvisoryCard
							key={a.id}
							id={a.id}
							severity={a.severity}
							title={a.title}
							summary={a.summary}
							affectedHosts={a.affected_hosts}
							patchUrl={a.patch_url}
						/>
					))}
				</div>
			)}
		</div>
	);
}
