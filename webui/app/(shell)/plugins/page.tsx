'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { ManifestValidator } from '@/components/plugins/manifest-validator';
import { PluginCard } from '@/components/plugins/plugin-card';
import { Button } from '@/components/primitives/button';
import { Tabs, TabsContent } from '@/components/primitives/tabs';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface Plugin {
	id: string;
	version: string;
	name: string;
	state: 'disabled' | 'enabled' | 'paused' | 'broken';
	capabilities?: string[];
}

interface PluginManifest {
	id: string;
	version: string;
	name: string;
	runtime: 'binary' | 'python' | 'node' | 'jvm' | 'wasm';
	capabilities?: string[];
	min_hl_helper_version: string;
	resources: {
		cpu_milli: number;
		memory_mib: number;
		disk_mib: number;
	};
	description?: string;
}

export default function PluginsPage() {
	const [showInstallDialog, setShowInstallDialog] = useState(false);
	const [validManifest, setValidManifest] = useState<PluginManifest | null>(null);
	const [isInstalling, setIsInstalling] = useState(false);

	const {
		data: plugins = [],
		isLoading,
		refetch,
	} = useQuery({
		queryKey: ['plugins'],
		queryFn: async () => {
			const data = await apiFetch<{ plugins: Plugin[] }>('/v1/plugins');
			return data.plugins;
		},
	});

	const handleInstall = async () => {
		if (!validManifest) return;

		setIsInstalling(true);
		try {
			await apiFetch('/v1/plugins', {
				method: 'POST',
				body: JSON.stringify(validManifest),
			});
			setShowInstallDialog(false);
			setValidManifest(null);
			refetch();
		} catch (err) {
			console.error('Failed to install plugin:', err);
		} finally {
			setIsInstalling(false);
		}
	};

	return (
		<div className="flex flex-col gap-8 p-8">
			<div className="flex items-center justify-between">
				<h1 className="text-2xl font-bold text-text">Plugins</h1>
			</div>

			<Tabs
				tabs={[
					{ label: 'Installed', value: 'installed' },
					{ label: 'Marketplace', value: 'marketplace' },
				]}
			>
				<TabsContent value="installed">
					{isLoading ? (
						<BlueprintSkeleton rows={3} />
					) : plugins.length === 0 ? (
						<EmptyState
							title="No plugins installed"
							description="Install your first plugin to get started"
						/>
					) : (
						<div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
							{plugins.map(plugin => (
								<PluginCard
									key={plugin.id}
									id={plugin.id}
									version={plugin.version}
									name={plugin.name}
									state={plugin.state}
									capabilities={plugin.capabilities}
									onStateChange={() => refetch()}
								/>
							))}
						</div>
					)}
					<div className="pt-6">
						<Button onClick={() => setShowInstallDialog(true)} type="button">
							Install Plugin
						</Button>
					</div>
				</TabsContent>

				<TabsContent value="marketplace">
					<EmptyState title="Plugin Marketplace" description="Coming in Phase 2" />
				</TabsContent>
			</Tabs>

			{/* Install Dialog */}
			{showInstallDialog && (
				<div className="fixed inset-0 flex items-center justify-center bg-canvas/80 z-50">
					<div className="max-w-2xl w-full mx-4 bg-surface rounded border border-hairline p-8">
						<h2 className="text-xl font-bold text-text mb-6">Install Plugin</h2>
						<ManifestValidator
							onValid={setValidManifest}
							onInvalid={() => setValidManifest(null)}
						/>
						<div className="flex gap-4 justify-end mt-8">
							<Button
								variant="ghost"
								onClick={() => {
									setShowInstallDialog(false);
									setValidManifest(null);
								}}
								type="button"
							>
								Cancel
							</Button>
							<Button
								onClick={handleInstall}
								disabled={!validManifest || isInstalling}
								type="button"
							>
								{isInstalling ? 'Installing...' : 'Install'}
							</Button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
