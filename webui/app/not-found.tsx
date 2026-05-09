import Link from 'next/link';

export default function NotFound() {
	return (
		<div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
			<div className="font-mono text-6xl font-bold text-text-dim/40">404</div>
			<h1 className="text-h2 text-text">Page not found</h1>
			<p className="max-w-md font-mono text-sm text-text-dim">
				This route doesn't exist. If you arrived here from a link in the app, the target may have
				moved or been renamed.
			</p>
			<div className="mt-2 flex gap-2">
				<Link
					href="/hosts"
					className="rounded-sm border border-accent bg-accent/15 px-3 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-accent hover:bg-accent/25"
				>
					Hosts
				</Link>
				<Link
					href="/"
					className="rounded-sm border border-hairline bg-surface-2 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-text-dim hover:text-text"
				>
					Home
				</Link>
			</div>
		</div>
	);
}
