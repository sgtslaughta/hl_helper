'use client';

interface SwitchProps {
	id?: string;
	checked?: boolean;
	onCheckedChange?: (checked: boolean) => void;
	disabled?: boolean;
	label?: string;
}

export function Switch({
	id,
	checked = false,
	onCheckedChange,
	disabled = false,
	label,
}: SwitchProps) {
	const switchId = id || `switch-${Math.random().toString(36).slice(2)}`;

	const handleClick = () => {
		if (!disabled && onCheckedChange) {
			onCheckedChange(!checked);
		}
	};

	return (
		<div className="flex items-center gap-3">
			<button
				type="button"
				id={switchId}
				role="switch"
				aria-checked={checked}
				disabled={disabled}
				onClick={handleClick}
				className={`relative inline-flex h-6 w-11 rounded-full transition-colors ${
					checked ? 'bg-accent' : 'bg-surface-2'
				} ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
			>
				<span
					className={`inline-block h-5 w-5 transform rounded-full bg-canvas transition-transform ${
						checked ? 'translate-x-5' : 'translate-x-0.5'
					}`}
				/>
			</button>
			{label && (
				<label htmlFor={switchId} className="cursor-pointer text-small text-text">
					{label}
				</label>
			)}
		</div>
	);
}
