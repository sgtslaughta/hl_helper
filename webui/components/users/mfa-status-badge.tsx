'use client';

import { AlertCircle, Shield } from 'lucide-react';

interface MFAStatusBadgeProps {
	enabled: boolean;
	lastMfaAt?: string | null;
}

export function MFAStatusBadge({ enabled, lastMfaAt }: MFAStatusBadgeProps) {
	if (!enabled) {
		return (
			<div className="inline-flex items-center gap-1 rounded px-2 py-1 text-small font-semibold text-warn">
				<AlertCircle className="h-4 w-4" />
				MFA Disabled
			</div>
		);
	}

	return (
		<div className="inline-flex items-center gap-1 rounded px-2 py-1 text-small font-semibold text-ok">
			<Shield className="h-4 w-4" />
			MFA Enabled
			{lastMfaAt && <span className="text-tiny text-text-dim">{lastMfaAt}</span>}
		</div>
	);
}
