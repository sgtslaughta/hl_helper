'use client';

import { useDocsModeStore } from '@/stores/docs-mode';
import { AlertOctagon, AlertTriangle, Info, Lightbulb } from 'lucide-react';
import type { ReactNode } from 'react';
import { SecurityNote } from '../security/security-note';

export function BeginnerOnly({ children }: { children: ReactNode }) {
	const mode = useDocsModeStore(s => s.mode);
	if (mode === 'advanced') return null;
	return <>{children}</>;
}

export function AdvancedOnly({ children }: { children: ReactNode }) {
	const mode = useDocsModeStore(s => s.mode);
	if (mode === 'beginner') return null;
	return <>{children}</>;
}

interface CalloutProps {
	type: 'info' | 'warn' | 'danger' | 'tip';
	children: ReactNode;
}

function Callout({ type, children }: CalloutProps) {
	const icons = {
		info: <Info className="h-5 w-5" />,
		warn: <AlertTriangle className="h-5 w-5" />,
		danger: <AlertOctagon className="h-5 w-5" />,
		tip: <Lightbulb className="h-5 w-5" />,
	};

	const colors = {
		info: 'border-l-blue-500 bg-blue-50 text-blue-900',
		warn: 'border-l-yellow-500 bg-yellow-50 text-yellow-900',
		danger: 'border-l-red-500 bg-red-50 text-red-900',
		tip: 'border-l-green-500 bg-green-50 text-green-900',
	};

	return (
		<div className={`border-l-4 ${colors[type]} rounded-r p-4 my-4 flex gap-3`}>
			<div className="flex-shrink-0">{icons[type]}</div>
			<div className="flex-1">{children}</div>
		</div>
	);
}

export const mdxComponents = {
	h1: (props: React.HTMLAttributes<HTMLElement>) => (
		<h1 className="text-4xl font-bold text-text mt-8 mb-4 font-serif" {...props} />
	),
	h2: (props: React.HTMLAttributes<HTMLElement>) => (
		<h2 className="text-3xl font-bold text-text mt-6 mb-3 font-serif" {...props} />
	),
	h3: (props: React.HTMLAttributes<HTMLElement>) => (
		<h3 className="text-2xl font-semibold text-text mt-4 mb-2 font-serif" {...props} />
	),
	p: (props: React.HTMLAttributes<HTMLElement>) => (
		<p className="text-base text-text leading-relaxed my-4 font-serif" {...props} />
	),
	code: (props: React.HTMLAttributes<HTMLElement>) => (
		<code className="bg-surface-2 px-2 py-1 rounded font-mono text-sm text-text-dim" {...props} />
	),
	pre: (props: React.HTMLAttributes<HTMLElement>) => (
		<pre
			className="bg-surface-2 border border-hairline rounded p-4 overflow-x-auto my-4 font-mono text-sm text-text-dim"
			{...props}
		/>
	),
	blockquote: (props: React.HTMLAttributes<HTMLElement>) => (
		<blockquote
			className="border-l-4 border-accent pl-4 py-2 my-4 text-text-dim italic"
			{...props}
		/>
	),
	a: (props: React.HTMLAttributes<HTMLElement>) => <a className="text-accent hover:text-accent-dim underline" {...props} />,
	table: (props: React.HTMLAttributes<HTMLElement>) => (
		<table className="w-full border-collapse my-4 border border-hairline" {...props} />
	),
	th: (props: React.HTMLAttributes<HTMLElement>) => (
		<th
			className="border border-hairline bg-surface-2 px-4 py-2 text-left font-semibold text-text"
			{...props}
		/>
	),
	td: (props: React.HTMLAttributes<HTMLElement>) => <td className="border border-hairline px-4 py-2 text-text" {...props} />,
	ul: (props: React.HTMLAttributes<HTMLElement>) => <ul className="list-disc list-inside my-4 text-text space-y-2" {...props} />,
	ol: (props: React.HTMLAttributes<HTMLElement>) => (
		<ol className="list-decimal list-inside my-4 text-text space-y-2" {...props} />
	),
	li: (props: React.HTMLAttributes<HTMLElement>) => <li className="text-base text-text" {...props} />,
	Callout,
	BeginnerOnly,
	AdvancedOnly,
	SecurityNote,
};
