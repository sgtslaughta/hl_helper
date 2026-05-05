'use client';

import { Button } from '@/components/primitives/button';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { RotateCcw } from 'lucide-react';
import { useState } from 'react';

interface SecretRefRowProps {
	ref: string;
	backend: string;
	lastAccessed?: string | null;
}

export function SecretRefRow({ ref, backend, lastAccessed }: SecretRefRowProps) {
	const [isLoading, setIsLoading] = useState(false);
	const canRotate = useCan('secret:rotate');

	const handleRotate = async () => {
		setIsLoading(true);
		try {
			await apiFetch(`/v1/secrets/${ref}/rotate`, {
				method: 'POST',
			});
		} catch (err) {
			console.error('Failed to rotate secret:', err);
		} finally {
			setIsLoading(false);
		}
	};

	return (
		<tr className="border-t border-hairline hover:bg-surface-2">
			<td className="px-4 py-3 text-small text-text">{ref}</td>
			<td className="px-4 py-3 text-small text-text-dim">{backend}</td>
			<td className="px-4 py-3 text-small text-text-dim">
				{lastAccessed ? new Date(lastAccessed).toLocaleString() : 'Never'}
			</td>
			<td className="px-4 py-3 text-right">
				{canRotate && (
					<Button
						size="sm"
						variant="ghost"
						onClick={handleRotate}
						disabled={isLoading}
						type="button"
						className="gap-2"
					>
						<RotateCcw className="h-4 w-4" />
						{isLoading ? 'Rotating...' : 'Rotate'}
					</Button>
				)}
			</td>
		</tr>
	);
}
