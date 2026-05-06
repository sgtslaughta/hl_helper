'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { apiFetch } from './api-client';

export interface User {
	id: string;
	username?: string;
	email: string;
	full_name?: string;
	created_at?: string;
	roles: string[];
	permissions?: string[];
	groups?: string[];
}

export interface Session {
	user: User;
	authenticated: boolean;
}

// Backend /v1/auth/whoami returns a flat shape: {id, email, roles, groups}.
// Wrap into Session for legacy callers.
interface WhoamiResponse {
	id: string;
	email: string;
	roles: string[];
	groups: string[];
}

export function useAuth() {
	const router = useRouter();
	const {
		data: session,
		isLoading,
		error,
	} = useQuery({
		queryKey: ['auth', 'session'],
		queryFn: async (): Promise<Session | null> => {
			try {
				const r = await apiFetch<WhoamiResponse>('/v1/auth/whoami');
				return {
					user: { id: r.id, email: r.email, roles: r.roles, groups: r.groups },
					authenticated: true,
				};
			} catch {
				return null;
			}
		},
		staleTime: Number.POSITIVE_INFINITY,
	});

	const login = async (username: string, password: string): Promise<void> => {
		const response = await apiFetch<{ mfa_required?: boolean }>('/v1/auth/login', {
			method: 'POST',
			body: JSON.stringify({ username, password }),
		});
		if (!response.mfa_required) {
			router.refresh();
		}
	};

	const logout = async (): Promise<void> => {
		await apiFetch('/v1/auth/logout', { method: 'POST' });
		router.push('/login');
	};

	return {
		user: session?.user,
		authenticated: session?.authenticated ?? false,
		isLoading,
		error,
		login,
		logout,
	};
}
