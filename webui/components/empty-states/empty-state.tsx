'use client';

interface EmptyStateProps {
	title: string;
	description?: string;
	icon?: React.ReactNode;
	action?: {
		label: string;
		onClick: () => void;
	};
}

export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
	return (
		<div className="flex flex-col items-center justify-center py-12">
			{icon && <div className="mb-4 text-4xl">{icon}</div>}
			<h2 className="mb-2 text-h3 text-text">{title}</h2>
			{description && <p className="mb-6 text-text-dim">{description}</p>}
			{action && (
				<button
					type="button"
					onClick={action.onClick}
					className="rounded bg-accent px-4 py-2 text-canvas hover:bg-accent-dim"
				>
					{action.label}
				</button>
			)}
		</div>
	);
}
