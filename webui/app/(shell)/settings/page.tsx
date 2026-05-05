'use client';

export const dynamic = 'force-dynamic';

import { SettingRow } from '@/components/settings/setting-row';
import { BlueprintSkeleton } from '@/components/skeletons/blueprint-skeleton';
import { apiFetch } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface Setting {
	key: string;
	value: string;
	source: 'runtime' | 'env' | 'file' | 'default';
	scope?: 'runtime-mutable' | 'read-only';
}

interface SettingsResponse {
	settings: Setting[];
}

export default function SettingsPage() {
	const { data: settings = [], isLoading } = useQuery({
		queryKey: ['settings'],
		queryFn: async () => {
			const data = await apiFetch<SettingsResponse>('/v1/settings');
			return data.settings;
		},
	});

	// Group settings by key prefix
	const groupedSettings: Record<string, Setting[]> = {};
	for (const setting of settings) {
		const prefix = setting.key.split('.')[0];
		if (!groupedSettings[prefix]) {
			groupedSettings[prefix] = [];
		}
		groupedSettings[prefix].push(setting);
	}

	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">Settings</h1>
				<p className="text-text-dim mt-2">Configure application behavior and parameters</p>
			</div>

			{isLoading ? (
				<BlueprintSkeleton rows={5} />
			) : (
				<div className="flex flex-col gap-12">
					{Object.entries(groupedSettings).map(([prefix, prefixSettings]) => (
						<div key={prefix}>
							<h2 className="mb-4 text-lg font-semibold text-text capitalize">{prefix}</h2>
							<div className="overflow-x-auto rounded border border-hairline">
								<table className="w-full">
									<thead className="bg-surface-2">
										<tr>
											<th className="px-4 py-3 text-left text-small font-semibold text-text">
												Key
											</th>
											<th className="px-4 py-3 text-left text-small font-semibold text-text">
												Value
											</th>
											<th className="px-4 py-3 text-left text-small font-semibold text-text">
												Source
											</th>
											<th className="px-4 py-3 text-right text-small font-semibold text-text">
												Actions
											</th>
										</tr>
									</thead>
									<tbody>
										{prefixSettings.map(setting => (
											<SettingRow
												key={setting.key}
												value={setting.value}
												source={setting.source}
												scope={setting.scope}
											/>
										))}
									</tbody>
								</table>
							</div>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
