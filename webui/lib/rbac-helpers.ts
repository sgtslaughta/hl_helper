'use client';

import { useAuth } from './auth';

export function useCan(action: string, scope?: string): boolean {
	const { user } = useAuth();

	if (!user) return false;

	// Check exact permission match
	const permission = scope ? `${action}:${scope}` : action;
	if (user.permissions?.includes(permission)) return true;

	// Check wildcard permission
	if (user.permissions?.includes(`${action}:*`)) return true;
	if (user.permissions?.includes('*')) return true;

	// Role-based fallback for owner / admin: both grant universal access.
	// Backend whoami now ships permissions=["*"] for owner role, but keep
	// this fallback for stale sessions and future role variants.
	if (user.roles?.includes('owner')) return true;
	if (user.roles?.includes('admin')) return true;

	return false;
}
