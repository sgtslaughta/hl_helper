"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getHostExposure, type HostExposureSummary } from "@/lib/api/hosts";
import { apiFetch } from "@/lib/api-client";

export function HostExposurePanel({ hostId }: { hostId: string }) {
	const qc = useQueryClient();
	const { data } = useQuery<HostExposureSummary>({
		queryKey: ["host-exposure", hostId],
		queryFn: () => getHostExposure(hostId),
		refetchInterval: 60_000,
	});

	// Unified scan: triggers package inventory + exposure scan + risk recompute
	// via the existing /v1/hosts/{id}/rescan endpoint.
	const fullScan = useMutation({
		mutationFn: () =>
			apiFetch(`/v1/hosts/${encodeURIComponent(hostId)}/rescan`, { method: "POST" }),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: ["host-exposure", hostId] });
			qc.invalidateQueries({ queryKey: ["host-risk", hostId] });
			qc.invalidateQueries({ queryKey: ["host-posture", hostId] });
			qc.invalidateQueries({ queryKey: ["host-advisories", hostId] });
		},
	});

	if (!data) return <div className="text-sm text-zinc-500">Loading exposure…</div>;

	const tiers: Array<[keyof HostExposureSummary["counts"], string]> = [
		["NETWORK_EXPOSED", "Network-Exposed"],
		["ACTIVE", "Active"],
		["INSTALLED_ONLY", "Dormant"],
		["UNKNOWN", "Unknown"],
	];

	return (
		<div className="rounded border border-zinc-800 bg-zinc-950 p-4 text-sm">
			<header className="mb-3 flex items-center justify-between">
				<h3 className="font-semibold">Runtime Exposure</h3>
				<span className="text-xs text-zinc-500">
					{data.last_scan_at ? `Last scan ${new Date(data.last_scan_at).toLocaleString()}` : "Never scanned"}
				</span>
			</header>
			<dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
				{tiers.map(([key, label]) => (
					<div key={key} className="contents">
						<dt className="text-zinc-500">{label}</dt>
						<dd>{data.counts[key] ?? 0}</dd>
					</div>
				))}
			</dl>
			<button
				type="button"
				onClick={() => fullScan.mutate()}
				disabled={fullScan.isPending}
				className="mt-3 rounded border border-zinc-700 px-3 py-1 hover:bg-zinc-800 disabled:opacity-40"
				title="Inventory + exposure scan + risk recompute"
			>
				{fullScan.isPending ? "Scanning…" : "Run full scan"}
			</button>
		</div>
	);
}
