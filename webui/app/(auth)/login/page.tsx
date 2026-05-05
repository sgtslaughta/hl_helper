'use client';

import { apiFetch } from '@/lib/api-client';
import { useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

type Mode = 'password' | 'admin-token';

function LoginInner() {
	const searchParams = useSearchParams();
	const next = searchParams.get('next') || '/hosts';

	const [mode, setMode] = useState<Mode>('password');
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');
	const [adminToken, setAdminToken] = useState('');
	const [error, setError] = useState<string | null>(null);
	const [pending, setPending] = useState(false);

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		setError(null);
		setPending(true);
		try {
			if (mode === 'admin-token') {
				await apiFetch('/v1/auth/admin-token-login', {
					method: 'POST',
					body: JSON.stringify({ token: adminToken.trim() }),
				});
			} else {
				await apiFetch('/v1/auth/login', {
					method: 'POST',
					body: JSON.stringify({ username, password }),
				});
			}
			window.location.assign(next);
		} catch (err) {
			setError(err instanceof Error ? err.message : 'Login failed');
		} finally {
			setPending(false);
		}
	};

	return (
		<div className="w-full max-w-md rounded-lg border border-hairline bg-surface p-8">
			<h1 className="mb-2 text-h1 text-text">Sign In</h1>
			<p className="mb-6 text-small text-text-dim">
				{mode === 'admin-token'
					? 'Paste the admin token printed at server start.'
					: 'Sign in with your account.'}
			</p>

			<div className="mb-6 flex gap-1 rounded border border-hairline bg-surface-2 p-1 text-small">
				<button
					type="button"
					onClick={() => setMode('password')}
					className={`flex-1 rounded px-3 py-1.5 transition-colors ${
						mode === 'password'
							? 'bg-accent text-canvas font-semibold'
							: 'text-text-dim hover:text-text'
					}`}
				>
					Password
				</button>
				<button
					type="button"
					onClick={() => setMode('admin-token')}
					className={`flex-1 rounded px-3 py-1.5 transition-colors ${
						mode === 'admin-token'
							? 'bg-accent text-canvas font-semibold'
							: 'text-text-dim hover:text-text'
					}`}
				>
					Admin Token
				</button>
			</div>

			<form onSubmit={handleSubmit} className="space-y-4">
				{mode === 'password' ? (
					<>
						<div>
							<label htmlFor="login-username" className="block text-small text-text">
								Username or email
							</label>
							<input
								id="login-username"
								type="text"
								autoComplete="username"
								value={username}
								onChange={e => setUsername(e.target.value)}
								className="mt-2 w-full rounded border border-hairline bg-surface-2 px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent"
								placeholder="owner@example.com"
								required
							/>
						</div>
						<div>
							<label htmlFor="login-password" className="block text-small text-text">
								Password
							</label>
							<input
								id="login-password"
								type="password"
								autoComplete="current-password"
								value={password}
								onChange={e => setPassword(e.target.value)}
								className="mt-2 w-full rounded border border-hairline bg-surface-2 px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent"
								placeholder="••••••••"
								required
							/>
						</div>
					</>
				) : (
					<div>
						<label htmlFor="admin-token" className="block text-small text-text">
							Admin token
						</label>
						<input
							id="admin-token"
							type="password"
							autoComplete="off"
							value={adminToken}
							onChange={e => setAdminToken(e.target.value)}
							className="mt-2 w-full rounded border border-hairline bg-surface-2 px-3 py-2 font-mono text-tiny text-text outline-none placeholder:text-text-dim focus:border-accent"
							placeholder="64-char hex token from server log"
							required
						/>
						<p className="mt-2 text-tiny text-text-dim">
							Bootstrap-only. Use this on first launch, then create a real account through onboarding.
						</p>
					</div>
				)}

				{error && (
					<div className="rounded border border-danger bg-danger/10 px-3 py-2 text-small text-danger">
						{error}
					</div>
				)}

				<button
					type="submit"
					disabled={pending}
					className="w-full rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim disabled:opacity-50"
				>
					{pending ? 'Signing in…' : 'Sign In'}
				</button>
			</form>

			<div className="mt-6 border-t border-hairline pt-6 text-center text-small text-text-dim">
				SSO providers coming soon
			</div>
		</div>
	);
}

export default function LoginPage() {
	return (
		<Suspense fallback={<div className="h-screen w-screen bg-canvas" />}>
			<LoginInner />
		</Suspense>
	);
}
