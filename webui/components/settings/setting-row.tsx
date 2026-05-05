'use client';

import { Button } from '@/components/primitives/button';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { Check, X } from 'lucide-react';
import { useState } from 'react';
import { SourceBadge } from './source-badge';

interface SettingRowProps {
	key: string;
	value: string;
	source: 'runtime' | 'env' | 'file' | 'default';
	scope?: 'runtime-mutable' | 'read-only';
}

export function SettingRow({
	key,
	value: initialValue,
	source,
	scope = 'read-only',
}: SettingRowProps) {
	const [isEditing, setIsEditing] = useState(false);
	const [value, setValue] = useState(initialValue);
	const [isLoading, setIsLoading] = useState(false);
	const canWrite = useCan('setting:write');

	const isEditable = scope === 'runtime-mutable' && canWrite;

	const handleSave = async () => {
		setIsLoading(true);
		try {
			await apiFetch('/v1/settings', {
				method: 'PATCH',
				body: JSON.stringify({ [key]: value }),
			});
			setIsEditing(false);
		} catch (err) {
			console.error('Failed to save setting:', err);
			setValue(initialValue);
		} finally {
			setIsLoading(false);
		}
	};

	const handleCancel = () => {
		setValue(initialValue);
		setIsEditing(false);
	};

	return (
		<tr className="border-t border-hairline hover:bg-surface-2">
			<td className="px-4 py-3 text-small font-medium text-text">{key}</td>
			<td className="px-4 py-3 text-small text-text">
				{isEditing && isEditable ? (
					<input
						type="text"
						value={value}
						onChange={e => setValue(e.target.value)}
						className="rounded border border-hairline bg-surface px-2 py-1 text-text"
					/>
				) : (
					<span className="text-text-dim">{value}</span>
				)}
			</td>
			<td className="px-4 py-3">
				<SourceBadge source={source} />
			</td>
			<td className="px-4 py-3 text-right">
				{isEditable ? (
					<div className="flex gap-2">
						{isEditing ? (
							<>
								<Button
									size="sm"
									variant="ghost"
									onClick={handleSave}
									disabled={isLoading}
									type="button"
								>
									<Check className="h-4 w-4" />
								</Button>
								<Button
									size="sm"
									variant="ghost"
									onClick={handleCancel}
									disabled={isLoading}
									type="button"
								>
									<X className="h-4 w-4" />
								</Button>
							</>
						) : (
							<Button size="sm" variant="ghost" onClick={() => setIsEditing(true)} type="button">
								Edit
							</Button>
						)}
					</div>
				) : null}
			</td>
		</tr>
	);
}
