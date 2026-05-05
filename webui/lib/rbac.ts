'use client';

import { useAuth } from '@/lib/auth';
import type { ActionType } from '@/lib/risk-catalog';

const ADMIN_ACTIONS: ReadonlySet<ActionType> = new Set<ActionType>([
  'reboot',
  'shell-exec',
  'pkg-update',
  'revoke-host',
  'delete-host',
  'mint-enrollment-token',
  'revoke-enrollment-token',
]);

export interface CanPerform {
  allowed: boolean;
  reason?: string;
  principal?: string;
}

export function useCanPerform(action: ActionType): CanPerform {
  const { user, isLoading } = useAuth();
  if (isLoading) return { allowed: false, reason: 'Loading permissions…' };
  if (!user) return { allowed: false, reason: 'Not signed in.' };
  if (ADMIN_ACTIONS.has(action)) {
    if (user.roles.includes('admin')) return { allowed: true, principal: user.id };
    return { allowed: false, reason: 'Requires admin role.', principal: user.id };
  }
  return { allowed: true, principal: user.id };
}
