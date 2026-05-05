'use client';

import * as RadixCheckbox from '@radix-ui/react-checkbox';
import { Check } from 'lucide-react';

interface CheckboxProps {
	id?: string;
	checked?: boolean;
	onCheckedChange?: (checked: boolean) => void;
	disabled?: boolean;
	label?: string;
}

export function Checkbox({ id, checked, onCheckedChange, disabled, label }: CheckboxProps) {
	const checkboxId = id || `checkbox-${Math.random().toString(36).slice(2)}`;
	return (
		<div className="flex items-center gap-2">
			<RadixCheckbox.Root
				id={checkboxId}
				checked={checked}
				onCheckedChange={onCheckedChange}
				disabled={disabled}
				className="flex h-5 w-5 items-center justify-center rounded border border-hairline bg-surface disabled:opacity-50"
			>
				<RadixCheckbox.Indicator className="text-accent">
					<Check className="h-4 w-4" />
				</RadixCheckbox.Indicator>
			</RadixCheckbox.Root>
			{label && (
				<label htmlFor={checkboxId} className="cursor-pointer text-small text-text">
					{label}
				</label>
			)}
		</div>
	);
}
