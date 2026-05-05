'use client';

import { Button } from '@/components/primitives/button';
import { Textarea } from '@/components/primitives/textarea';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

interface Route {
	channel: string;
	recipients: string[];
}

interface NotificationConfig {
	routes: Route[];
	templates?: string;
}

export default function NotificationsPage() {
	const [templates, setTemplates] = useState('');
	const [isSaving, setIsSaving] = useState(false);

	const { data: config } = useQuery({
		queryKey: ['notifications'],
		queryFn: async () => {
			return await apiFetch<NotificationConfig>('/v1/notifications');
		},
	});

	// Initialize templates from config
	useEffect(() => {
		if (config?.templates) {
			setTemplates(config.templates);
		}
	}, [config]);

	const handleSave = async () => {
		setIsSaving(true);
		try {
			await apiFetch('/v1/notifications', {
				method: 'PATCH',
				body: JSON.stringify({ templates }),
			});
		} catch (err) {
			console.error('Failed to save templates:', err);
		} finally {
			setIsSaving(false);
		}
	};

	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">Notifications</h1>
				<p className="text-text-dim mt-2">Configure notification channels and templates</p>
			</div>

			{/* Routes Table */}
			<div>
				<h2 className="text-lg font-semibold text-text mb-4">Routes</h2>
				<div className="overflow-x-auto rounded border border-hairline">
					<table className="w-full">
						<thead className="bg-surface-2">
							<tr>
								<th className="px-4 py-3 text-left text-small font-semibold text-text">Channel</th>
								<th className="px-4 py-3 text-left text-small font-semibold text-text">
									Recipients
								</th>
							</tr>
						</thead>
						<tbody>
							{config?.routes?.map(route => (
								<tr key={route.channel} className="border-t border-hairline hover:bg-surface-2">
									<td className="px-4 py-3 text-small text-text">{route.channel}</td>
									<td className="px-4 py-3 text-small text-text-dim">
										{route.recipients.join(', ')}
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</div>

			{/* Templates */}
			<div>
				<Textarea
					label="Notification Templates"
					hint="Markdown format"
					value={templates}
					onChange={e => setTemplates(e.target.value)}
					rows={12}
				/>
				<div className="mt-4">
					<Button onClick={handleSave} disabled={isSaving} type="button">
						{isSaving ? 'Saving...' : 'Save'}
					</Button>
				</div>
			</div>
		</div>
	);
}
