'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useMutation, useQuery } from '@tanstack/react-query';
import { formatRelative } from 'date-fns';
import { LogOut } from 'lucide-react';

interface Session {
	id: string;
	user_id: string;
	user_email: string;
	ip_address: string;
	user_agent: string;
	created_at: string;
	last_activity_at: string;
}

export default function SessionsPage() {
	const canRead = useCan('sessions:read');
	const canTerminate = useCan('sessions:terminate');

	const { data, isLoading } = useQuery<{ sessions: Session[] }>({
		queryKey: ['sessions'],
		queryFn: async () => {
			return await apiFetch('/v1/sessions');
		},
		enabled: canRead,
	});

	const terminateMutation = useMutation({
		mutationFn: async (sessionId: string) => {
			await apiFetch(`/v1/sessions/${sessionId}/terminate`, { method: 'POST' });
		},
	});

	if (!canRead) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view sessions"
				icon="🔒"
			/>
		);
	}

	const sessions = data?.sessions || [];

	return (
		<div className="flex flex-col gap-6 p-6">
			<div>
				<h1 className="text-h1 text-text">Active Sessions</h1>
				<p className="mt-2 text-text-dim">Manage user authentication sessions</p>
			</div>

			{isLoading ? (
				<div className="text-center text-text-dim">Loading sessions...</div>
			) : sessions.length === 0 ? (
				<EmptyState
					title="No sessions"
					description="No active sessions"
					icon={<LogOut className="h-8 w-8 text-text-dim" />}
				/>
			) : (
				<div className="overflow-x-auto">
					<table className="w-full text-small">
						<thead>
							<tr className="border-b border-hairline text-text-dim">
								<th className="px-4 py-2 text-left">User</th>
								<th className="px-4 py-2 text-left">IP Address</th>
								<th className="px-4 py-2 text-left">Created</th>
								<th className="px-4 py-2 text-left">Last Activity</th>
								{canTerminate && <th className="px-4 py-2 text-left">Action</th>}
							</tr>
						</thead>
						<tbody>
							{sessions.map(session => (
								<tr key={session.id} className="border-b border-hairline hover:bg-surface-2">
									<td className="px-4 py-2 font-semibold">{session.user_email}</td>
									<td className="px-4 py-2 font-mono text-text-dim">{session.ip_address}</td>
									<td className="px-4 py-2 text-text-dim">
										{formatRelative(new Date(session.created_at), new Date())}
									</td>
									<td className="px-4 py-2 text-text-dim">
										{formatRelative(new Date(session.last_activity_at), new Date())}
									</td>
									{canTerminate && (
										<td className="px-4 py-2">
											<button
												type="button"
												onClick={() => terminateMutation.mutate(session.id)}
												disabled={terminateMutation.isPending}
												className="rounded px-2 py-1 text-tiny font-semibold text-danger hover:bg-danger/20 disabled:opacity-50"
											>
												Terminate
											</button>
										</td>
									)}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</div>
	);
}
