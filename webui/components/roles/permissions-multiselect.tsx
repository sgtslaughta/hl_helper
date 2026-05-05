'use client';

import { Checkbox } from '@/components/primitives/checkbox';
import { Input } from '@/components/primitives/input';
import { useMemo, useState } from 'react';

interface PermissionsMultiselectProps {
	selected: string[];
	onChange: (selected: string[]) => void;
	availablePermissions: string[];
	disabled?: boolean;
}

export function PermissionsMultiselect({
	selected,
	onChange,
	availablePermissions,
	disabled,
}: PermissionsMultiselectProps) {
	const [searchTerm, setSearchTerm] = useState('');

	const filtered = useMemo(
		() => availablePermissions.filter(p => p.toLowerCase().includes(searchTerm.toLowerCase())),
		[searchTerm, availablePermissions],
	);

	const handleToggle = (perm: string) => {
		if (selected.includes(perm)) {
			onChange(selected.filter(p => p !== perm));
		} else {
			onChange([...selected, perm]);
		}
	};

	const handleSelectAll = () => {
		if (selected.length === filtered.length) {
			onChange(selected.filter(p => !filtered.includes(p)));
		} else {
			const newSelected = new Set(selected);
			for (const p of filtered) {
				newSelected.add(p);
			}
			onChange(Array.from(newSelected));
		}
	};

	return (
		<div className="flex flex-col gap-3">
			<Input
				placeholder="Search permissions..."
				value={searchTerm}
				onChange={e => setSearchTerm(e.target.value)}
				disabled={disabled}
			/>
			<div className="max-h-60 overflow-y-auto rounded border border-hairline bg-surface p-3">
				<div className="mb-2 pb-2 border-b border-hairline">
					<Checkbox
						label={`Select all (${filtered.length})`}
						checked={filtered.length > 0 && filtered.every(p => selected.includes(p))}
						onCheckedChange={handleSelectAll}
						disabled={disabled}
					/>
				</div>
				<div className="space-y-2">
					{filtered.map(perm => (
						<Checkbox
							key={perm}
							label={perm}
							checked={selected.includes(perm)}
							onCheckedChange={() => handleToggle(perm)}
							disabled={disabled}
						/>
					))}
				</div>
			</div>
			<div className="text-tiny text-text-dim">
				{selected.length} of {availablePermissions.length} selected
			</div>
		</div>
	);
}
