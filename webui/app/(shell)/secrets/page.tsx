'use client';

export const dynamic = 'force-dynamic';

import { Button } from '@/components/primitives/button';
import { Select } from '@/components/primitives/select';
import { SecretRefRow } from '@/components/secrets/secret-ref-row';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface Secret {
	ref: string;
	backend: string;
	lastAccessed?: string | null;
}

export default function SecretsPage() {
	const [backend, setBackend] = useState('local');

	const { data: secrets = [] } = useQuery({
		queryKey: ['secrets', backend],
		queryFn: async () => {
			const data = await apiFetch<{ secrets: Secret[] }>(`/v1/secrets?backend=${backend}`);
			return data.secrets;
		},
	});

	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">Secrets</h1>
				<p className="text-text-dim mt-2">Manage secret backends and references</p>
			</div>

			{/* Backend Selector */}
			<div className="flex gap-4">
				<Select
					label="Backend"
					value={backend}
					onValueChange={setBackend}
					options={[
						{ value: 'local', label: 'Local' },
						{ value: 'vault', label: 'Vault' },
					]}
				/>
			</div>

			{/* Secrets Table */}
			<div className="overflow-x-auto rounded border border-hairline">
				<table className="w-full">
					<thead className="bg-surface-2">
						<tr>
							<th className="px-4 py-3 text-left text-small font-semibold text-text">Reference</th>
							<th className="px-4 py-3 text-left text-small font-semibold text-text">Backend</th>
							<th className="px-4 py-3 text-left text-small font-semibold text-text">
								Last Accessed
							</th>
							<th className="px-4 py-3 text-right text-small font-semibold text-text">Actions</th>
						</tr>
					</thead>
					<tbody>
						{secrets.map(secret => (
							<SecretRefRow
								key={secret.ref}
								ref={secret.ref}
								backend={secret.backend}
								lastAccessed={secret.lastAccessed}
							/>
						))}
					</tbody>
				</table>
			</div>

			{/* Migration Card */}
			<div className="rounded border border-hairline bg-surface p-6">
				<h3 className="font-semibold text-text">Secret Backend Migration</h3>
				<p className="text-small text-text-dim mt-2">Migrate existing secrets to a new backend</p>
				<Button size="sm" variant="secondary" type="button" className="mt-4">
					Start Migration
				</Button>
			</div>
		</div>
	);
}
