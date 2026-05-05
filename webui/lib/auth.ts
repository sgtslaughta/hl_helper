'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { apiFetch } from './api-client';

export interface User {
	id: string;
	username: string;
	email: string;
	full_name?: string;
	created_at: string;
	roles: string[];
	permissions: string[];
}

export interface Session {
	user: User;
	authenticated: boolean;
}

export function useAuth() {
	const router = useRouter();
	const {
		data: session,
		isLoading,
		error,
	} = useQuery({
		queryKey: ['auth', 'session'],
		queryFn: async () => {
			try {
				const response = await apiFetch<Session>('/v1/auth/whoami');
				return response;
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
