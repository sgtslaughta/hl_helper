'use client';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { CircleUser, Lock, Mail, MessageCircle, Webhook, Wind } from 'lucide-react';

interface Integration {
	provider: string;
	configured: boolean;
	displayName: string;
	icon: React.ReactNode;
}

const PROVIDERS: Integration[] = [
	{
		provider: 'smtp',
		displayName: 'Email (SMTP)',
		icon: <Mail className="h-6 w-6" />,
		configured: false,
	},
	{
		provider: 'discord',
		displayName: 'Discord',
		icon: <MessageCircle className="h-6 w-6" />,
		configured: false,
	},
	{
		provider: 'slack',
		displayName: 'Slack',
		icon: <Wind className="h-6 w-6" />,
		configured: false,
	},
	{
		provider: 'webhook',
		displayName: 'Webhook',
		icon: <Webhook className="h-6 w-6" />,
		configured: false,
	},
	{
		provider: 'vault',
		displayName: 'HashiCorp Vault',
		icon: <Lock className="h-6 w-6" />,
		configured: false,
	},
	{
		provider: 'oidc',
		displayName: 'OpenID Connect',
		icon: <CircleUser className="h-6 w-6" />,
		configured: false,
	},
];

export default function IntegrationsPage() {
	const { data: integrations = [] } = useQuery({
		queryKey: ['integrations'],
		queryFn: async () => {
			const data = await apiFetch<{ integrations: { provider: string }[] }>('/v1/integrations');
			const configuredSet = new Set(data.integrations.map(i => i.provider));
			return PROVIDERS.map(p => ({
				...p,
				configured: configuredSet.has(p.provider),
			}));
		},
	});

	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">Integrations</h1>
				<p className="text-text-dim mt-2">Connect external services and platforms</p>
			</div>

			<div className="grid gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
				{integrations.map(integration => (
					<div
						key={integration.provider}
						className="flex flex-col gap-4 rounded border border-hairline bg-surface p-6"
					>
						<div className="text-accent">{integration.icon}</div>
						<div>
							<h3 className="font-semibold text-text">{integration.displayName}</h3>
							<p className="text-small text-text-dim mt-1">
								{integration.configured ? 'Connected' : 'Not configured'}
							</p>
						</div>
						<div>
							<Badge variant={integration.configured ? 'ok' : 'default'} size="sm">
								{integration.configured ? 'Configured' : 'Unconfigured'}
							</Badge>
						</div>
						<Button variant="secondary" size="sm" type="button">
							Configure
						</Button>
					</div>
				))}
			</div>
		</div>
	);
}
