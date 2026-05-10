'use client';

import type { Host, HostMetrics, HostSurvey, NetInterface } from '@/lib/api/hosts';
import {
	ChevronRight,
	Cpu,
	HardDrive,
	MemoryStick,
	CircuitBoard,
	Network,
	Server,
} from 'lucide-react';
import type { ComponentType } from 'react';

// proto uint64 fields are serialized as strings via MessageToDict (JS precision
// guard). Coerce defensively before arithmetic.
function asNum(v: unknown): number {
	if (typeof v === 'number') return v;
	if (typeof v === 'string') {
		const n = Number(v);
		return Number.isFinite(n) ? n : 0;
	}
	return 0;
}

function bytesToGB(bytes: unknown): string {
	return (asNum(bytes) / 1024 ** 3).toFixed(1);
}

function mbpsToStr(mbps: unknown): string {
	const n = asNum(mbps);
	if (n >= 1000) return `${(n / 1000).toFixed(1)} Gbps`;
	return `${Math.round(n)} Mbps`;
}

function formatTimestamp(ts: string | undefined): string {
	if (!ts) return '—';
	const d = new Date(ts);
	return d.toLocaleTimeString();
}

function bytesPerSec(n: number): string {
	if (n === 0) return "0 B/s";
	const units = ["B", "KB", "MB", "GB"];
	let i = 0;
	let v = n;
	while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
	return `${v.toFixed(1)} ${units[i]}/s`;
}

function NetInterfacesSection({ interfaces }: { interfaces: NetInterface[] }) {
	if (!interfaces || interfaces.length === 0) return null;
	return (
		<div className="flex flex-col">
			<RibbonHeader icon={Network} title="Network Interfaces" />
			<div className="mc-bezel space-y-2 px-2.5 py-2 font-mono text-[11px]">
				<ul className="space-y-1 text-sm font-mono">
					{interfaces.map((iface) => (
						<li key={iface.name} className="flex items-center gap-3 text-[10px]">
							<span className={iface.up ? "text-emerald-400" : "text-zinc-600"}>
								{iface.up ? "●" : "○"}
							</span>
							<span className="w-20">{iface.name}</span>
							<span className="w-32 text-zinc-400">{iface.ipv4?.[0] ?? "—"}</span>
							<span className="w-24">↓ {bytesPerSec(iface.rx_bps)}</span>
							<span className="w-24">↑ {bytesPerSec(iface.tx_bps)}</span>
							{iface.rx_errors + iface.tx_errors > 0 && (
								<span className="text-amber-400">⚠ {iface.rx_errors + iface.tx_errors} err</span>
							)}
						</li>
					))}
				</ul>
			</div>
		</div>
	);
}

function RibbonHeader({
	icon: Icon,
	title,
	onJump,
}: {
	icon: ComponentType<{ className?: string; size?: number }>;
	title: string;
	onJump?: () => void;
}) {
	return (
		<div className="mb-1.5 flex items-center justify-between">
			<div className="flex items-center gap-1.5">
				<Icon className="text-accent" size={11} />
				<span className="mc-heading">{title}</span>
			</div>
			{onJump ? (
				<button
					type="button"
					onClick={onJump}
					className="flex items-center gap-0.5 font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-accent"
				>
					Inspect <ChevronRight size={10} />
				</button>
			) : null}
		</div>
	);
}

export function HardwarePanel({ host }: { host: Host }) {
	const survey = host.survey as HostSurvey | undefined;
	const metrics = host.metrics as HostMetrics | undefined;

	return (
		<div className="space-y-3">
			{/* Hardware section */}
			<div className="flex flex-col">
				<RibbonHeader icon={Server} title="Hardware" />
				{survey ? (
					<div className="mc-bezel space-y-2 px-2.5 py-2 font-mono text-[11px]">
						{/* OS/Kernel/Arch row */}
						<div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">OS</div>
								<div className="mc-readout text-[12px] text-text">
									{survey.os ?? '—'} {survey.os_version ?? ''}
								</div>
							</div>
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">KERNEL</div>
								<div className="mc-readout text-[12px] text-text">{survey.kernel ?? '—'}</div>
							</div>
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">ARCH</div>
								<div className="mc-readout text-[12px] text-text">{survey.arch ?? '—'}</div>
							</div>
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">VIRT</div>
								<div className="mc-readout text-[12px] text-text">{survey.virt ?? '—'}</div>
							</div>
						</div>

						{/* CPU row */}
						<div className="border-t border-hairline pt-2">
							<div className="mb-1 flex items-center gap-1.5">
								<Cpu size={11} className="text-accent" />
								<span className="uppercase tracking-[0.14em] text-text-dim">CPU</span>
							</div>
							<div className="mc-readout text-[12px] text-text">{survey.cpu_model ?? '—'}</div>
							<div className="grid grid-cols-2 gap-2 text-[10px] text-text-dim">
								<span>{survey.cpu_cores ?? 0} cores</span>
								<span>{survey.cpu_threads ?? 0} threads</span>
							</div>
						</div>

						{/* Memory */}
						<div className="border-t border-hairline pt-2">
							<div className="mb-1 flex items-center gap-1.5">
								<MemoryStick size={11} className="text-accent" />
								<span className="uppercase tracking-[0.14em] text-text-dim">RAM</span>
							</div>
							<div className="mc-readout text-[12px] text-text">
								{bytesToGB(survey.mem_total_bytes)} GB
							</div>
							{/* mem_total_bytes coerced to number via bytesToGB above */}
						</div>

						{/* Disks */}
						{(survey.disks?.length ?? 0) > 0 ? (
							<div className="border-t border-hairline pt-2">
								<div className="mb-1 flex items-center gap-1.5">
									<HardDrive size={11} className="text-accent" />
									<span className="uppercase tracking-[0.14em] text-text-dim">Disks</span>
								</div>
								<div className="space-y-1">
									{(survey.disks ?? []).map(d => (
										<div key={d.device ?? d.mount ?? Math.random().toString()} className="text-[10px]">
											<div className="text-text">
												{d.device ?? '—'} @ {d.mount ?? '—'}
											</div>
											<div className="text-text-dim">
												{bytesToGB(d.size_bytes ?? 0)} GB ({d.fstype ?? '—'})
											</div>
										</div>
									))}
								</div>
							</div>
						) : null}

						{/* NICs */}
						{(survey.nics?.length ?? 0) > 0 ? (
							<div className="border-t border-hairline pt-2">
								<div className="mb-1 flex items-center gap-1.5">
									<Network size={11} className="text-accent" />
									<span className="uppercase tracking-[0.14em] text-text-dim">Interfaces</span>
								</div>
								<div className="space-y-1">
									{(survey.nics ?? []).map(n => (
										<div key={n.name} className="text-[10px]">
											<div className="flex items-center justify-between text-text">
												<span>{n.name}</span>
												<span className="text-text-dim">
													{mbpsToStr(n.speed_mbps ?? 0)}
												</span>
											</div>
											<div className="text-text-dim">{n.mac}</div>
											{(n.ipv4?.length ?? 0) > 0 ? (
												<div className="text-text-dim">{(n.ipv4 ?? []).join(', ')}</div>
											) : null}
										</div>
									))}
								</div>
							</div>
						) : null}

						{/* BIOS/Board */}
						<div className="border-t border-hairline pt-2">
							<div className="mb-1 flex items-center gap-1.5">
								<CircuitBoard size={11} className="text-accent" />
								<span className="uppercase tracking-[0.14em] text-text-dim">Firmware</span>
							</div>
							<div className="grid gap-1 text-[10px]">
								<div>
									<span className="text-text-dim">BIOS: </span>
									<span className="text-text">
										{survey.bios_vendor ?? '—'} {survey.bios_version ?? ''}
									</span>
								</div>
								<div>
									<span className="text-text-dim">Board: </span>
									<span className="text-text">
										{survey.board_vendor ?? '—'} {survey.board_product ?? ''}
									</span>
								</div>
							</div>
						</div>

						<div className="border-t border-hairline pt-2 text-[9px] text-text-dim">
							Surveyed {formatTimestamp(host.survey_at)}
						</div>
					</div>
				) : (
					<div className="mc-bezel px-2.5 py-2 font-mono text-[11px] text-text-dim">
						Not yet surveyed
					</div>
				)}
			</div>

			{/* Live metrics section */}
			<div className="flex flex-col">
				<RibbonHeader icon={Server} title="Live" />
				{metrics ? (
					<div className="mc-bezel space-y-2 px-2.5 py-2 font-mono text-[11px]">
						<div className="grid grid-cols-2 gap-2 md:grid-cols-3">
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">Load 1m</div>
								<div className="mc-readout text-[12px] text-text">
									{(metrics.load_1 ?? 0).toFixed(2)}
								</div>
							</div>
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">Load 5m</div>
								<div className="mc-readout text-[12px] text-text">
									{(metrics.load_5 ?? 0).toFixed(2)}
								</div>
							</div>
							<div>
								<div className="uppercase tracking-[0.14em] text-text-dim">Load 15m</div>
								<div className="mc-readout text-[12px] text-text">
									{(metrics.load_15 ?? 0).toFixed(2)}
								</div>
							</div>
						</div>
						<div className="border-t border-hairline pt-2">
							<div className="grid grid-cols-2 gap-2 md:grid-cols-3">
								<div>
									<div className="uppercase tracking-[0.14em] text-text-dim">Mem %</div>
									<div className="mc-readout text-[12px] text-text">
										{(metrics.mem_used_pct ?? 0).toFixed(0)}%
									</div>
								</div>
								<div>
									<div className="uppercase tracking-[0.14em] text-text-dim">Disk %</div>
									<div className="mc-readout text-[12px] text-text">
										{(metrics.disk_used_pct ?? 0).toFixed(0)}%
									</div>
								</div>
								<div>
									<div className="uppercase tracking-[0.14em] text-text-dim">Uptime</div>
									<div className="mc-readout text-[12px] text-text">
										{Math.floor(asNum(metrics.uptime_seconds) / 86400)}d
									</div>
								</div>
							</div>
						</div>
						<div className="border-t border-hairline pt-2 text-[9px] text-text-dim">
							{formatTimestamp(host.metrics_at)}
						</div>
					</div>
				) : (
					<div className="mc-bezel px-2.5 py-2 font-mono text-[11px] text-text-dim">
						No metrics yet
					</div>
				)}
			</div>

			{/* Network interfaces section */}
			<NetInterfacesSection interfaces={metrics?.interfaces ?? []} />
		</div>
	);
}
