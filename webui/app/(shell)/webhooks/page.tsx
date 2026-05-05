'use client';

export const dynamic = 'force-dynamic';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Tabs, TabsContent } from '@/components/primitives/tabs';
import { apiFetch } from '@/lib/api-client';
import { useCan } from '@/lib/rbac-helpers';
import { useQuery } from '@tanstack/react-query';
import { RotateCcw } from 'lucide-react';

interface Webhook {
	id: string;
	url: string;
	status: 'active' | 'failed' | 'inactive';
	lastDelivery?: string;
	direction: 'inbound' | 'outbound';
}

export default function WebhooksPage() {
	const canWrite = useCan('webhook:write');

	const { data: inbound = [] } = useQuery({
		queryKey: ['webhooks', 'inbound'],
		queryFn: async () => {
			const data = await apiFetch<{ webhooks: Webhook[] }>('/v1/webhooks?direction=inbound');
			return data.webhooks;
		},
	});

	const { data: outbound = [] } = useQuery({
		queryKey: ['webhooks', 'outbound'],
		queryFn: async () => {
			const data = await apiFetch<{ webhooks: Webhook[] }>('/v1/webhooks?direction=outbound');
			return data.webhooks;
		},
	});

	const renderTable = (webhooks: Webhook[]) => (
		<div className="overflow-x-auto rounded border border-hairline">
			<table className="w-full">
				<thead className="bg-surface-2">
					<tr>
						<th className="px-4 py-3 text-left text-small font-semibold text-text">URL</th>
						<th className="px-4 py-3 text-left text-small font-semibold text-text">Status</th>
						<th className="px-4 py-3 text-left text-small font-semibold text-text">
							Last Delivery
						</th>
						<th className="px-4 py-3 text-right text-small font-semibold text-text">Actions</th>
					</tr>
				</thead>
				<tbody>
					{webhooks.map(webhook => (
						<tr key={webhook.id} className="border-t border-hairline hover:bg-surface-2">
							<td className="px-4 py-3 text-small text-text">{webhook.url}</td>
							<td className="px-4 py-3">
								<Badge variant={webhook.status === 'active' ? 'ok' : 'danger'} size="sm">
									{webhook.status}
								</Badge>
							</td>
							<td className="px-4 py-3 text-small text-text-dim">
								{webhook.lastDelivery ? new Date(webhook.lastDelivery).toLocaleString() : 'Never'}
							</td>
							<td className="px-4 py-3 text-right">
								{canWrite && (
									<Button size="sm" variant="ghost" type="button" className="gap-2">
										<RotateCcw className="h-4 w-4" />
										Rotate
									</Button>
								)}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);

	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">Webhooks</h1>
				<p className="text-text-dim mt-2">Manage inbound and outbound webhook endpoints</p>
			</div>

			<Tabs
				tabs={[
					{ label: 'Inbound', value: 'inbound' },
					{ label: 'Outbound', value: 'outbound' },
				]}
			>
				<TabsContent value="inbound">
					{inbound.length > 0 ? (
						renderTable(inbound)
					) : (
						<p className="text-text-dim">No inbound webhooks</p>
					)}
				</TabsContent>
				<TabsContent value="outbound">
					{outbound.length > 0 ? (
						renderTable(outbound)
					) : (
						<p className="text-text-dim">No outbound webhooks</p>
					)}
				</TabsContent>
			</Tabs>
		</div>
	);
}
