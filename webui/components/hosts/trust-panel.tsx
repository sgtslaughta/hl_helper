'use client';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { useCan } from '@/lib/rbac-helpers';

interface TrustInfo {
	trusted: boolean;
	certificateSHA: string;
	issuedAt: string;
	expiresAt: string;
	issuer: string;
}

interface TrustPanelProps {
	hostId?: string;
	trustInfo: TrustInfo;
	onRevoke?: () => void;
}

export function TrustPanel({ trustInfo, onRevoke }: TrustPanelProps) {
	const canManageTrust = useCan('manage', 'trust');

	return (
		<div className="space-y-4">
			<div className="rounded border border-hairline bg-surface p-4">
				<div className="flex items-center justify-between mb-4">
					<h3 className="text-sm font-semibold text-text">Trust Status</h3>
					<Badge variant={trustInfo.trusted ? 'ok' : 'danger'} size="sm">
						{trustInfo.trusted ? 'Trusted' : 'Untrusted'}
					</Badge>
				</div>

				<div className="space-y-3 text-xs">
					<div>
						<span className="block text-xs font-semibold text-text-dim mb-1">Certificate SHA</span>
						<code className="block bg-surface-2 px-2 py-1 rounded text-text font-mono break-all">
							{trustInfo.certificateSHA}
						</code>
					</div>

					<div className="grid grid-cols-2 gap-4">
						<div>
							<span className="block text-xs font-semibold text-text-dim mb-1">Issued At</span>
							<p className="text-text">{trustInfo.issuedAt}</p>
						</div>
						<div>
							<span className="block text-xs font-semibold text-text-dim mb-1">Expires At</span>
							<p className="text-text">{trustInfo.expiresAt}</p>
						</div>
					</div>

					<div>
						<span className="block text-xs font-semibold text-text-dim mb-1">Issuer</span>
						<p className="text-text">{trustInfo.issuer}</p>
					</div>
				</div>

				{canManageTrust && trustInfo.trusted && (
					<div className="mt-4 pt-4 border-t border-hairline">
						<Button variant="danger" size="sm" onClick={onRevoke} type="button">
							Revoke Trust
						</Button>
					</div>
				)}
			</div>
		</div>
	);
}
