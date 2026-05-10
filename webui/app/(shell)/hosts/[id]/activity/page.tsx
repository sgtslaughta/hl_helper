'use client';

export const dynamic = 'force-dynamic';

import { ActivityTimeline } from '@/components/hosts/activity/activity-timeline';
import { TempPolicyPill } from '@/components/hosts/activity/temp-policy-pill';
import { getPolicy } from '@/lib/api/logs';
import { useParams } from 'next/navigation';
import useSWR from 'swr';

export default function HostActivityPage() {
	const params = useParams<{ id: string }>();
	const hostId = params.id;

	const { data: policy, mutate: refetchPolicy } = useSWR(
		['policy', hostId],
		async () => {
			try {
				return await getPolicy(`host:${hostId}`);
			} catch (e) {
				return null;
			}
		},
		{
			revalidateOnFocus: false,
			refreshInterval: 10_000, // Refresh every 10s to update countdown
		},
	);

	const hasActiveTempPolicy = policy?.expires_at && new Date(policy.expires_at).getTime() > Date.now();

	return (
		<div className="flex flex-col gap-4 p-6">
			<div className="flex items-baseline justify-between">
				<h1 className="text-h1 text-text">Host Activity</h1>
				<div className="flex items-center gap-3">
					{hasActiveTempPolicy && policy?.expires_at && (
						<TempPolicyPill
							hostId={hostId}
							expiresAt={policy.expires_at}
							onDeleted={() => refetchPolicy()}
						/>
					)}
					<div className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
						host {hostId.slice(0, 12)}
					</div>
				</div>
			</div>

			<ActivityTimeline hostId={hostId} />
		</div>
	);
}
