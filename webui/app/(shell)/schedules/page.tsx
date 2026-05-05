'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Button } from '@/components/primitives/button';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface Schedule {
	id: string;
	name: string;
	cron: string;
	nextFire?: string;
	enabled: boolean;
}

export default function SchedulesPage() {
	const queryClient = useQueryClient();
	const [, setEditingId] = useState<string | null>(null);
	void setEditingId;

	const { data, isLoading, isError } = useQuery({
		queryKey: ['schedules'],
		queryFn: () => apiFetch<Schedule[]>('/v1/schedules'),
	});

	const toggleMutation = useMutation({
		mutationFn: async (id: string) => {
			return apiFetch(`/v1/schedules/${id}/toggle`, {
				method: 'POST',
			});
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['schedules'] });
		},
	});

	if (isLoading) return <BlueprintSkeleton rows={8} />;
	if (isError || !data) return <EmptyState title="Failed to load schedules" />;
	if (data.length === 0)
		return <EmptyState title="No schedules" description="Create a schedule to automate tasks" />;

	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Schedules</h1>
				<p className="text-text-dim">Manage automated task scheduling</p>
			</div>

			<div className="rounded border border-hairline bg-surface overflow-hidden">
				<table className="w-full text-sm">
					<thead className="border-b border-hairline bg-surface-2">
						<tr>
							<th className="px-4 py-3 text-left font-semibold text-text">Name</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Cron Expression</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Next Fire</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Enabled</th>
							<th className="px-4 py-3 text-left font-semibold text-text">Actions</th>
						</tr>
					</thead>
					<tbody>
						{data.map(schedule => (
							<tr
								key={schedule.id}
								className="border-b border-hairline hover:bg-surface-2 transition-colors"
							>
								<td className="px-4 py-3 text-sm text-text">{schedule.name}</td>
								<td className="px-4 py-3 text-sm text-text-dim font-mono">{schedule.cron}</td>
								<td className="px-4 py-3 text-sm text-text-dim">{schedule.nextFire || '—'}</td>
								<td className="px-4 py-3">
									<input
										type="checkbox"
										checked={schedule.enabled}
										onChange={() => toggleMutation.mutate(schedule.id)}
										className="rounded"
									/>
								</td>
								<td className="px-4 py-3">
									<Button variant="ghost" size="sm" type="button">
										Edit
									</Button>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}
