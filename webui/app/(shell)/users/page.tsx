'use client';

import { EmptyState } from '@/components/empty-states/empty-state';

import { UserForm } from '@/components/users/user-form';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Users } from 'lucide-react';
import { useState } from 'react';

interface User {
	id: string;
	email: string;
	display_name: string | null;
	kind: string;
	disabled: boolean;
	created_at: string;
	roles: string[];
}

export default function UsersPage() {
	const [showCreate, setShowCreate] = useState(false);
	const canRead = useCan('users:read');
	const canCreate = useCan('users:create');

	const { data, isLoading } = useQuery<{ users: User[] }>({
		queryKey: ['users'],
		queryFn: async () => {
			return await apiFetch('/v1/users');
		},
		enabled: canRead,
	});

	const createMutation = useMutation({
		mutationFn: async (userData: { email: string; kind: string }) => {
			await apiFetch('/v1/users', {
				method: 'POST',
				body: JSON.stringify(userData),
			});
		},
		onSuccess: () => {
			setShowCreate(false);
		},
	});

	if (!canRead) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view users"
				icon="🔒"
			/>
		);
	}

	const users = data?.users || [];

	return (
		<div className="flex flex-col gap-6 p-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-h1 text-text">Users</h1>
					<p className="mt-2 text-text-dim">Manage local and SSO users</p>
				</div>
				{canCreate && (
					<button
						type="button"
						onClick={() => setShowCreate(!showCreate)}
						className="rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim"
					>
						{showCreate ? 'Cancel' : 'New User'}
					</button>
				)}
			</div>

			{showCreate && canCreate && (
				<div className="rounded border border-hairline bg-surface-2 p-4">
					<h2 className="mb-4 text-h3 text-text">Create User</h2>
					<UserForm
						onSubmit={async data => {
							await createMutation.mutateAsync(data);
						}}
						isLoading={createMutation.isPending}
					/>
				</div>
			)}

			{isLoading ? (
				<div className="text-center text-text-dim">Loading users...</div>
			) : users.length === 0 ? (
				<EmptyState
					title="No users"
					description="Create your first user to get started"
					icon={<Users className="h-8 w-8 text-text-dim" />}
					action={
						canCreate ? { label: 'Create User', onClick: () => setShowCreate(true) } : undefined
					}
				/>
			) : (
				<div className="overflow-x-auto">
					<table className="w-full text-small">
						<thead>
							<tr className="border-b border-hairline text-text-dim">
								<th className="px-4 py-2 text-left">Email</th>
								<th className="px-4 py-2 text-left">Name</th>
								<th className="px-4 py-2 text-left">Kind</th>
								<th className="px-4 py-2 text-left">Status</th>
								<th className="px-4 py-2 text-left">Roles</th>
							</tr>
						</thead>
						<tbody>
							{users.map(user => (
								<tr key={user.id} className="border-b border-hairline hover:bg-surface-2">
									<td className="px-4 py-2">{user.email}</td>
									<td className="px-4 py-2 text-text-dim">{user.display_name || '—'}</td>
									<td className="px-4 py-2">
										<span className="rounded bg-surface px-2 py-1 text-tiny">{user.kind}</span>
									</td>
									<td className="px-4 py-2">
										{user.disabled ? (
											<span className="text-warn">Disabled</span>
										) : (
											<span className="text-ok">Active</span>
										)}
									</td>
									<td className="px-4 py-2 text-accent">{user.roles.join(', ')}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</div>
	);
}
