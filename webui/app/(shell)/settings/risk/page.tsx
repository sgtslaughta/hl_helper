'use client';

import { apiFetch } from '@/lib/api-client';
import { useState } from 'react';

const TIERS = [
	{ key: 'NETWORK_EXPOSED', label: 'Network-Exposed', defaultValue: 2.0 },
	{ key: 'ACTIVE', label: 'Active', defaultValue: 1.5 },
	{ key: 'INSTALLED_ONLY', label: 'Dormant', defaultValue: 0.5 },
	{ key: 'UNKNOWN', label: 'Unknown', defaultValue: 1.0 },
];

function ExposureMultiplierSettings() {
	const [values, setValues] = useState<Record<string, number>>(
		Object.fromEntries(TIERS.map(t => [t.key, t.defaultValue]))
	);
	const [saving, setSaving] = useState(false);

	async function save(key: string, value: number) {
		setSaving(true);
		try {
			await apiFetch(`/v1/settings/risk.exposure_multiplier.${key}`, {
				method: 'PUT',
				body: JSON.stringify({ value }),
				headers: { 'Content-Type': 'application/json' },
			});
		} finally {
			setSaving(false);
		}
	}

	return (
		<section className="space-y-3">
			<h3 className="font-semibold">Vulnerability Exposure Weighting</h3>
			<p className="text-sm text-zinc-500">
				Multipliers applied to base CVSS contribution per advisory tier.
			</p>
			{TIERS.map((t) => (
				<div key={t.key} className="flex items-center gap-3">
					<label className="w-40 text-sm">{t.label}</label>
					<input
						type="number"
						step="0.1"
						min="0"
						max="10"
						value={values[t.key]}
						onChange={(e) => setValues({ ...values, [t.key]: parseFloat(e.target.value) })}
						onBlur={() => save(t.key, values[t.key])}
						disabled={saving}
						className="w-20 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm disabled:opacity-50"
					/>
					<span className="text-xs text-zinc-500">default {t.defaultValue}</span>
				</div>
			))}
		</section>
	);
}

export default function RiskPage() {
	return (
		<div className="flex flex-col gap-4 p-6">
			<h1 className="text-h1 text-text">Risk Settings</h1>
			<p className="text-text-dim text-sm">
				Configure risk calculation parameters and weighting overrides.
			</p>

			<div className="rounded border border-hairline bg-surface p-4">
				<ExposureMultiplierSettings />
			</div>
		</div>
	);
}
