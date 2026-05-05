'use client';

import { useState } from 'react';

export default function LoginPage() {
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		// TODO: wire to useAuth().login()
		console.log('Login attempt:', { username, password });
	};

	return (
		<div className="w-full max-w-md rounded-lg border border-hairline bg-surface p-8">
			<h1 className="mb-6 text-h1 text-text">Sign In</h1>

			<form onSubmit={handleSubmit} className="space-y-4">
				<div>
					<label htmlFor="login-username" className="block text-small text-text">Username</label>
					<input
						id="login-username"
						type="text"
						value={username}
						onChange={e => setUsername(e.target.value)}
						className="mt-2 w-full rounded border border-hairline bg-surface-2 px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent"
						placeholder="admin"
					/>
				</div>

				<div>
					<label htmlFor="login-password" className="block text-small text-text">Password</label>
					<input
						id="login-password"
						type="password"
						value={password}
						onChange={e => setPassword(e.target.value)}
						className="mt-2 w-full rounded border border-hairline bg-surface-2 px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent"
						placeholder="••••••••"
					/>
				</div>

				<button
					type="submit"
					className="w-full rounded bg-accent px-4 py-2 font-semibold text-canvas hover:bg-accent-dim"
				>
					Sign In
				</button>
			</form>

			<div className="mt-6 border-t border-hairline pt-6 text-center text-small text-text-dim">
				SSO providers coming soon
			</div>
		</div>
	);
}
