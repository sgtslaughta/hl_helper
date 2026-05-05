'use client';

import * as RadixSelect from '@radix-ui/react-select';
import { ChevronDown } from 'lucide-react';

interface SelectProps {
	value?: string;
	onValueChange?: (value: string) => void;
	disabled?: boolean;
	label?: string;
	placeholder?: string;
	options: Array<{ value: string; label: string }>;
}

export function Select({
	value,
	onValueChange,
	disabled,
	label,
	placeholder = 'Select...',
	options,
}: SelectProps) {
	return (
		<div className="flex flex-col gap-2">
			{label && <span className="text-small font-semibold text-text">{label}</span>}
			<RadixSelect.Root value={value} onValueChange={onValueChange} disabled={disabled}>
				<RadixSelect.Trigger className="inline-flex items-center justify-between rounded border border-hairline bg-surface px-3 py-2 text-text disabled:opacity-50">
					<RadixSelect.Value placeholder={placeholder} />
					<RadixSelect.Icon asChild>
						<ChevronDown className="h-4 w-4" />
					</RadixSelect.Icon>
				</RadixSelect.Trigger>
				<RadixSelect.Portal>
					<RadixSelect.Content className="rounded border border-hairline bg-surface-2 shadow-lg">
						<RadixSelect.Viewport className="p-1">
							{options.map(opt => (
								<RadixSelect.Item
									key={opt.value}
									value={opt.value}
									className="relative flex cursor-pointer select-none items-center rounded px-3 py-2 text-text hover:bg-surface"
								>
									<RadixSelect.ItemText>{opt.label}</RadixSelect.ItemText>
								</RadixSelect.Item>
							))}
						</RadixSelect.Viewport>
					</RadixSelect.Content>
				</RadixSelect.Portal>
			</RadixSelect.Root>
		</div>
	);
}
