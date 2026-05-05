'use client';

interface SecurityNoteProps {
	title: string;
	description: string;
	docsLink?: string;
}

export function SecurityNote({ title, description, docsLink }: SecurityNoteProps) {
	return (
		<div className="inline-flex items-start gap-2 rounded bg-surface-2 px-3 py-2">
			<span className="text-accent">ℹ</span>
			<div>
				<div className="font-semibold text-text">{title}</div>
				<div className="text-small text-text-dim">{description}</div>
				{docsLink && (
					<a href={docsLink} className="text-small text-accent hover:text-accent-dim">
						Learn more →
					</a>
				)}
			</div>
		</div>
	);
}
