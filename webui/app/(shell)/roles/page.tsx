'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { CapabilityChip } from '@/components/security/capability-chip';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface Role {
	id: string;
	name: string;
	description: string | null;
	built_in: boolean;
	permissions: string[];
	created_at: string;
}

export default function RolesPage() {
	const canRead = useCan('roles:read');
	const [expandedRole, setExpandedRole] = useState<string | null>(null);

	const { data, isLoading } = useQuery<{ roles: Role[] }>({
		queryKey: ['roles'],
		queryFn: async () => {
			return await apiFetch('/v1/roles');
		},
		enabled: canRead,
	});

	if (!canRead) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view roles"
				icon="🔒"
			/>
		);
	}

	const roles = data?.roles || [];
	const builtIn = roles.filter(r => r.built_in);
	const custom = roles.filter(r => !r.built_in);

	return (
		<div className="flex flex-col gap-6 p-6">
			<div>
				<h1 className="text-h1 text-text">Roles</h1>
				<p className="mt-2 text-text-dim">Define permissions and assign to users</p>
			</div>

			{isLoading ? (
				<div className="text-center text-text-dim">Loading roles...</div>
			) : (
				<>
					<div>
						<h2 className="mb-3 text-h3 text-text">Built-in Roles</h2>
						<div className="space-y-3">
							{builtIn.map(role => (
								<div key={role.id} className="rounded border border-hairline bg-surface p-4">
									<button
										type="button"
										onClick={() => setExpandedRole(expandedRole === role.id ? null : role.id)}
										className="flex w-full items-center justify-between"
									>
										<div className="text-left">
											<h3 className="font-semibold text-text">{role.name}</h3>
											{role.description && (
												<p className="text-small text-text-dim">{role.description}</p>
											)}
										</div>
										<span className="rounded bg-surface-2 px-2 py-1 text-tiny text-text-dim">
											{role.permissions.length} perms
										</span>
									</button>
									{expandedRole === role.id && (
										<div className="mt-4 flex flex-wrap gap-2 border-t border-hairline pt-4">
											{role.permissions.map(perm => (
												<CapabilityChip key={perm} permission={perm} />
											))}
										</div>
									)}
								</div>
							))}
						</div>
					</div>

					{custom.length > 0 && (
						<div>
							<h2 className="mb-3 text-h3 text-text">Custom Roles</h2>
							<div className="space-y-3">
								{custom.map(role => (
									<div key={role.id} className="rounded border border-hairline bg-surface p-4">
										<button
											type="button"
											onClick={() => setExpandedRole(expandedRole === role.id ? null : role.id)}
											className="flex w-full items-center justify-between"
										>
											<div className="text-left">
												<h3 className="font-semibold text-text">{role.name}</h3>
												{role.description && (
													<p className="text-small text-text-dim">{role.description}</p>
												)}
											</div>
											<span className="rounded bg-surface-2 px-2 py-1 text-tiny text-text-dim">
												{role.permissions.length} perms
											</span>
										</button>
										{expandedRole === role.id && (
											<div className="mt-4 flex flex-wrap gap-2 border-t border-hairline pt-4">
												{role.permissions.map(perm => (
													<CapabilityChip key={perm} permission={perm} />
												))}
											</div>
										)}
									</div>
								))}
							</div>
						</div>
					)}
				</>
			)}
		</div>
	);
}
