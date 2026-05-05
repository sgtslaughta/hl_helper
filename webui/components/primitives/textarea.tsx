'use client';

import React from 'react';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
	label?: string;
	error?: string;
	hint?: string;
	required?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
	({ label, error, hint, required, id, ...props }, ref) => {
		const textareaId = id || `textarea-${Math.random().toString(36).slice(2)}`;
		return (
			<div className="flex flex-col gap-2">
				{label && (
					<label htmlFor={textareaId} className="text-small font-semibold text-text">
						{label}
						{required && <span className="text-danger">*</span>}
					</label>
				)}
				<textarea
					ref={ref}
					id={textareaId}
					{...props}
					className="rounded border border-hairline bg-surface px-3 py-2 text-text placeholder:text-text-dim focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
				/>
				{hint && <span className="text-small text-text-dim">{hint}</span>}
				{error && <span className="text-small text-danger">{error}</span>}
			</div>
		);
	},
);

Textarea.displayName = 'Textarea';
