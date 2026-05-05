'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function ShellError({
	error,
	reset,
}: {
	error: Error & { digest?: string };
	reset: () => void;
}) {
	const router = useRouter();

	useEffect(() => {
		console.error('Shell error:', error);
	}, [error]);

	const isAuthError =
		error.message?.toLowerCase().includes('unauthorized') ||
		error.message?.toLowerCase().includes('401') ||
		error.message?.toLowerCase().includes('forbidden');

	return (
		<div className="flex h-screen w-screen items-center justify-center bg-canvas p-6">
			<div className="max-w-md rounded-lg border border-hairline bg-surface p-8 text-center">
				<h1 className="mb-2 text-h2 text-text">{isAuthError ? 'Sign in required' : 'Something broke'}</h1>
				<p className="mb-6 text-small text-text-dim">
					{isAuthError
						? 'Your session expired or you are not signed in.'
						: error.message || 'Unexpected error.'}
				</p>
				<div className="flex justify-center gap-2">
					{isAuthError ? (
						<button
							type="button"
							onClick={() => router.push('/login')}
							className="rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim"
						>
							Go to login
						</button>
					) : (
						<button
							type="button"
							onClick={() => reset()}
							className="rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim"
						>
							Retry
						</button>
					)}
				</div>
				{error.digest && (
					<p className="mt-4 font-mono text-small text-text-dim">digest: {error.digest}</p>
				)}
			</div>
		</div>
	);
}
