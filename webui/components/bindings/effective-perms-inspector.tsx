'use client';

import { Input } from '@/components/primitives/input';
import { CapabilityChip } from '@/components/security/capability-chip';
import { apiFetch } from '@/lib/api-client';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

interface EffectivePermsInspectorProps {
	isOpen: boolean;
	onClose: () => void;
}

export function EffectivePermsInspector({ isOpen, onClose }: EffectivePermsInspectorProps) {
	const [userId, setUserId] = useState('');

	const inspectMutation = useMutation<{ permissions: string[] }>({
		mutationFn: async () => {
			return await apiFetch(`/v1/bindings/inspector?principal_id=${userId}`);
		},
	});

	if (!isOpen) return null;

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
			<div className="w-full max-w-2xl rounded bg-surface p-6">
				<h2 className="mb-4 text-h3 text-text">Effective Permissions Inspector</h2>
				<div className="mb-4 flex gap-2">
					<Input
						placeholder="Enter user ID or email"
						value={userId}
						onChange={e => setUserId(e.target.value)}
					/>
					<button
						type="button"
						onClick={() => inspectMutation.mutate()}
						disabled={!userId || inspectMutation.isPending}
						className="rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim disabled:opacity-50"
					>
						Inspect
					</button>
				</div>

				{inspectMutation.isSuccess && (
					<div className="rounded bg-surface-2 p-4">
						<div className="mb-3 flex items-center gap-2">
							<CheckCircle2 className="h-5 w-5 text-ok" />
							<span className="font-semibold text-text">
								{inspectMutation.data.permissions.length} permissions
							</span>
						</div>
						<div className="flex flex-wrap gap-2">
							{inspectMutation.data.permissions.map(perm => (
								<CapabilityChip key={perm} permission={perm} />
							))}
						</div>
					</div>
				)}

				{inspectMutation.isError && (
					<div className="rounded bg-danger/20 px-4 py-3 text-danger">
						Failed to inspect permissions
					</div>
				)}

				<button
					type="button"
					onClick={onClose}
					className="mt-4 rounded border border-hairline px-4 py-2 text-text hover:bg-surface-2"
				>
					Close
				</button>
			</div>
		</div>
	);
}
