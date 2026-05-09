import type { ExposureTier } from "@/lib/api/hosts";

const STYLE: Record<ExposureTier, { label: string; cls: string }> = {
	NETWORK_EXPOSED: { label: "Network-Exposed", cls: "bg-red-950 text-red-300 ring-red-900" },
	ACTIVE: { label: "Active", cls: "bg-amber-950 text-amber-300 ring-amber-900" },
	INSTALLED_ONLY: { label: "Dormant", cls: "bg-zinc-900 text-zinc-400 ring-zinc-800" },
	UNKNOWN: { label: "Unknown", cls: "bg-slate-900 text-slate-400 ring-slate-800" },
};

export function ExposureBadge({ tier }: { tier: ExposureTier }) {
	const s = STYLE[tier];
	return (
		<span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs ring-1 ${s.cls}`}>
			● {s.label}
		</span>
	);
}
