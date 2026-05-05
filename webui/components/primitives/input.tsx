'use client';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
	label?: string;
	error?: string;
	required?: boolean;
}

export function Input({ label, error, required, id, ...props }: InputProps) {
	const inputId = id || `input-${Math.random().toString(36).slice(2)}`;
	return (
		<div className="flex flex-col gap-2">
			{label && (
				<label htmlFor={inputId} className="text-small font-semibold text-text">
					{label}
					{required && <span className="text-danger">*</span>}
				</label>
			)}
			<input
				id={inputId}
				{...props}
				className="rounded border border-hairline bg-surface px-3 py-2 text-text placeholder:text-text-dim focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
			/>
			{error && <span className="text-small text-danger">{error}</span>}
		</div>
	);
}
