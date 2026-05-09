'use client';

import { apiFetch } from '@/lib/api-client';
import { useHostAdvisories } from '@/lib/api/advisories';
import type { Host } from '@/lib/api/hosts';
import { fmtDuration, parseServerTime, relTime } from '@/lib/time';
import NumberFlow, { type Format as NumberFlowFormat } from '@number-flow/react';
import { useQuery } from '@tanstack/react-query';
import {
	Activity,
	AlertTriangle,
	Check,
	ChevronRight,
	CircleDashed,
	Cpu,
	Fingerprint,
	HardDrive,
	Loader2,
	MemoryStick,
	Minus,
	Network,
	ScrollText,
	Server,
	Timer,
	TrendingDown,
	TrendingUp,
	X,
} from 'lucide-react';
import { type ComponentType, type ReactNode, useEffect, useRef, useState } from 'react';

export type FocusMode =
	| 'overview'
	| 'hardware'
	| 'posture'
	| 'audit'
	| 'tasks'
	| 'advisories'
	| 'labels'
	| 'files'
	| 'network'
	| 'updates';

interface TaskItem {
	id: string;
	kind: string;
	status: string;
	created_at: string;
	risk: string;
	summary?: string;
}
interface TasksPage {
	items: TaskItem[];
	next_cursor: string | null;
}

interface AuditEntry {
	sequence: number;
	timestamp: string;
	actor: string;
	action: string;
	subject: string | null;
	payload: Record<string, unknown>;
	prev_hash: string;
	entry_hash: string;
}
interface AuditPage {
	items: AuditEntry[];
	next_cursor: string | null;
}

interface Finding {
	id: string;
	severity: string;
	title: string;
	summary: string;
	rule: string;
	subject_kind: string;
	subject_id: string | null;
}
interface PostureResponse {
	findings: Finding[];
}

interface Props {
	host: Host;
	onJump: (mode: FocusMode) => void;
}

function uptimeFmt(s: number | undefined): string {
	if (!s) return '–';
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	if (d > 0) return `${d}d ${h}h`;
	const m = Math.floor((s % 3600) / 60);
	return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function labelTone(key: string): string {
	const k = key.toLowerCase();
	if (k === 'os' || k === 'platform') return 'border-accent/40 text-accent';
	if (k === 'arch' || k === 'architecture') return 'border-ok/40 text-ok';
	if (k === 'os_version' || k === 'version') return 'border-accent/40 text-accent';
	if (k === 'kernel') return 'border-warn/40 text-warn';
	if (k === 'agent_version') return 'border-accent/40 text-accent';
	if (k === 'hostname') return 'border-text-dim text-text-dim';
	if (k === 'env' || k === 'environment') return 'border-warn/40 text-warn';
	if (k === 'role' || k === 'tier') return 'border-danger/40 text-danger';
	return 'border-hairline text-text-dim';
}

// Rolling buffer of recent samples driven by `tick` (per-heartbeat token).
// Returns up to `max` most recent values, oldest first. Skips updating when
// the value is undefined so transient gaps don't blank the trace.
// 5 minutes of history at 5-second heartbeats = 60 samples.
function useSamples(value: number | undefined, tick: string | number | undefined, max = 60): number[] {
	const [buf, setBuf] = useState<number[]>([]);
	useEffect(() => {
		if (value == null) return;
		setBuf(prev => {
			const next = prev.length >= max ? prev.slice(prev.length - max + 1) : prev.slice();
			next.push(value);
			return next;
		});
	}, [tick, value, max]);
	return buf;
}

// Picks a status CSS var based on the slope across the sample buffer.
// Compares the first 25% to the last 25% (averaged) so single-sample
// noise doesn't flip the color. Threshold uses relative change in
// percent of the average — keeps the response stable across metrics
// with very different absolute scales (load vs bps).
function trendStatusVar(samples: number[]): string {
	if (samples.length < 4) return 'var(--color-status-online)';
	const window = Math.max(2, Math.floor(samples.length / 4));
	const first = samples.slice(0, window);
	const last = samples.slice(-window);
	const avg = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
	const a = avg(first);
	const b = avg(last);
	const baseline = Math.max(Math.abs(a), Math.abs(b), 1);
	const rel = (b - a) / baseline; // -1 .. +1-ish
	if (rel > 0.15) return 'var(--color-status-crit)';
	if (rel > 0.05) return 'var(--color-status-warn)';
	if (rel < -0.05) return 'var(--color-status-online)';
	return 'var(--color-text-dim)';
}

// Reserved vertical band, in px, that the sparkline occupies at the
// bottom of each gauge. Gauge padding-bottom must be ≥ this so values/sub
// text never overlap the trace.
const SPARKLINE_H = 14;

function Sparkline({
	values,
	color,
	height = SPARKLINE_H,
}: {
	values: number[];
	color: string; // CSS color (currentColor inheritance preferred)
	height?: number;
}) {
	// Capped at ~SPARKLINE_H so the gauge can reserve a matching padding
	// (see GAUGE_PAD_BOTTOM below) without the trace bleeding into text.
	if (values.length < 2) return null;
	const w = 100;
	const h = height;
	const min = Math.min(...values);
	const max = Math.max(...values);
	const range = max - min || 1;
	const stepX = w / (values.length - 1);
	const pts = values.map((v, i) => {
		const x = i * stepX;
		// Reserve top/bottom 1px so the stroke isn't clipped by the bezel.
		const y = h - 1 - ((v - min) / range) * (h - 2);
		return `${x.toFixed(2)},${y.toFixed(2)}`;
	});
	const polyline = pts.join(' ');
	const areaPath = `M0,${h} L${pts.join(' L')} L${w},${h} Z`;
	return (
		<svg
			className="absolute inset-x-0 bottom-0 w-full overflow-visible"
			style={{ height, color }}
			viewBox={`0 0 ${w} ${h}`}
			preserveAspectRatio="none"
			aria-hidden="true"
		>
			<path d={areaPath} fill="currentColor" opacity={0.16} />
			<polyline
				points={polyline}
				fill="none"
				stroke="currentColor"
				strokeWidth={1.2}
				strokeLinejoin="round"
				strokeLinecap="round"
				vectorEffect="non-scaling-stroke"
				style={{ filter: 'drop-shadow(0 0 3px currentColor)' }}
			/>
			{/* Trailing dot at most-recent sample */}
			{(() => {
				const lastX = (values.length - 1) * stepX;
				const lastY = h - 1 - ((values[values.length - 1] - min) / range) * (h - 2);
				return (
					<circle
						cx={lastX}
						cy={lastY}
						r={1.6}
						fill="currentColor"
						style={{ filter: 'drop-shadow(0 0 4px currentColor)' }}
					/>
				);
			})()}
		</svg>
	);
}

// Tracks the sign of the most recent change in `value`. Default is
// neutral (0). On a real change the sign is set to ±1 and held briefly
// so the arrow is visible, then auto-resets back to 0. `tick` is an
// optional per-heartbeat token that lets a flat-but-still-arriving
// sample reaffirm neutral immediately (skips waiting for the timer).
function useDeltaSign(
	value: number | undefined,
	tick: string | number | undefined,
	eps = 0,
	holdMs = 4500,
): -1 | 0 | 1 | null {
	const [sign, setSign] = useState<-1 | 0 | 1 | null>(0);
	const lastRef = useRef<number | undefined>(undefined);
	useEffect(() => {
		if (value == null) return;
		const last = lastRef.current;
		lastRef.current = value;
		if (last == null) return;
		const d = value - last;
		if (Math.abs(d) < eps) {
			setSign(0);
			return;
		}
		setSign(d > 0 ? 1 : -1);
		const t = setTimeout(() => setSign(0), holdMs);
		return () => clearTimeout(t);
	}, [value, tick, eps, holdMs]);
	return sign;
}

// Animated numeric display. Falls back to em-dash when value is null so the
// dial reads stable while data loads. Wrapped suffix is rendered outside
// NumberFlow so it doesn't animate.
function AnimNum({
	value,
	suffix,
	format,
}: {
	value: number | null | undefined;
	suffix?: string;
	format?: NumberFlowFormat;
}) {
	if (value == null || !Number.isFinite(value)) return <span>—</span>;
	return (
		<span className="inline-flex items-baseline">
			<NumberFlow value={value} format={format} />
			{suffix ? <span className="ml-0.5">{suffix}</span> : null}
		</span>
	);
}

function deltaTone(sign: -1 | 0 | 1 | null): string {
	if (sign === 1) return 'text-danger';
	if (sign === -1) return 'text-ok';
	return 'text-text-dim';
}

function DeltaArrow({ sign }: { sign: -1 | 0 | 1 | null }) {
	const cls = `shrink-0 ${deltaTone(sign)}`;
	if (sign === 1) return <TrendingUp className={cls} size={12} strokeWidth={2.5} />;
	if (sign === -1) return <TrendingDown className={cls} size={12} strokeWidth={2.5} />;
	// sign null (no prior sample) or 0: render dim minus as steady-state placeholder.
	return <Minus className={cls} size={12} strokeWidth={2.5} />;
}

function Gauge({
	icon: Icon,
	iconTone = 'text-accent',
	label,
	value,
	pct,
	sub,
	numeric,
	tick,
	neutral,
}: {
	icon: ComponentType<{ className?: string; size?: number }>;
	// Static theme color for the icon (per-metric identity).
	iconTone?: string;
	label: string;
	value: ReactNode;
	pct?: number;
	sub?: string;
	// Raw scalar used for delta tracking. When omitted, falls back to `pct`.
	numeric?: number;
	// Per-sample token (e.g. metrics_at). Forces the indicator to re-evaluate
	// each heartbeat even when `numeric` is identical, so a flat metric
	// renders neutral instead of a stale arrow.
	tick?: string | number;
	// Suppress direction arrow + force neutral text tone (e.g. UPTIME).
	neutral?: boolean;
}) {
	const sign = useDeltaSign(numeric ?? pct, tick);
	const valueTone = neutral ? 'text-text' : deltaTone(sign);
	const samples = useSamples(numeric ?? pct, tick);
	// Trend tone: compare the average of the early window to the late
	// window across the full buffer. Picks status color from the slope
	// rather than the absolute pct, so a calm-but-rising metric goes
	// red even before it crosses 75% / 90% thresholds.
	const trendTone = neutral ? undefined : trendStatusVar(samples);
	return (
		<div
			className="mc-bezel relative flex items-center gap-2.5 overflow-hidden px-2.5 pt-2"
			// Reserve `SPARKLINE_H + 4px` so trace + small gap fits under the
			// readout. Gauges without a sparkline get the same padding for
			// vertical alignment in the grid.
			style={{ paddingBottom: SPARKLINE_H + 4 }}
		>
			<Icon className={`shrink-0 ${iconTone}`} size={16} />
			<div className="min-w-0 flex-1">
				<div className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-dim">
					{label}
				</div>
				<div className={`mc-readout flex items-center gap-1 text-[15px] font-semibold ${valueTone}`}>
					{typeof value === 'string' || typeof value === 'number' ? (
						<span>{value}</span>
					) : (
						value
					)}
					{neutral ? null : <DeltaArrow sign={sign} />}
				</div>
				{sub ? (
					<div className="font-mono text-[9px] uppercase tracking-wider text-text-dim">{sub}</div>
				) : null}
			</div>
			{!neutral && trendTone ? (
				<Sparkline values={samples} color={trendTone} />
			) : null}
		</div>
	);
}

function StatusBeacon({ status }: { status: string }) {
	const tone =
		{
			healthy: 'text-ok',
			online: 'text-ok',
			warning: 'text-warn',
			critical: 'text-danger',
			offline: 'text-text-dim',
			pending: 'text-accent',
			revoked: 'text-danger',
		}[status] ?? 'text-text-dim';
	return (
		<span className={`mc-pip ${tone} border-current`}>
			<span
				className={`mc-led ${status === 'healthy' || status === 'online' ? 'mc-led-pulse' : ''}`}
			/>
			{status.toUpperCase()}
		</span>
	);
}

function RibbonHeader({
	icon: Icon,
	title,
	count,
	onJump,
	tone,
}: {
	icon: ComponentType<{ className?: string; size?: number }>;
	title: string;
	count?: number;
	onJump?: () => void;
	tone?: string;
}) {
	return (
		<div className="mb-1.5 flex items-center justify-between">
			<div className="flex items-center gap-1.5">
				<Icon className={tone ?? 'text-accent'} size={11} />
				<span className="mc-heading">{title}</span>
				{count != null && count > 0 ? (
					<span className="mc-readout font-mono text-[10px] text-text-dim">[{count}]</span>
				) : null}
			</div>
			{onJump ? (
				<button
					type="button"
					onClick={onJump}
					className="flex items-center gap-0.5 font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-accent"
				>
					Open <ChevronRight size={10} />
				</button>
			) : null}
		</div>
	);
}

function severityTone(sev: string): string {
	switch (sev.toLowerCase()) {
		case 'critical':
		case 'high':
			return 'text-danger';
		case 'medium':
			return 'text-warn';
		case 'low':
			return 'text-accent';
		default:
			return 'text-text-dim';
	}
}

function statusTone(status: string): string {
	switch (status) {
		case 'completed':
		case 'succeeded':
			return 'text-ok';
		case 'running':
			return 'text-accent';
		case 'failed':
			return 'text-danger';
		case 'partial':
		case 'cancelled':
			return 'text-warn';
		default:
			return 'text-text-dim';
	}
}

function fmtBps(bps: number): string {
	if (!Number.isFinite(bps) || bps < 0) return '—';
	if (bps < 1024) return `${bps.toFixed(0)} B/s`;
	if (bps < 1024 ** 2) return `${(bps / 1024).toFixed(1)} KB/s`;
	if (bps < 1024 ** 3) return `${(bps / 1024 ** 2).toFixed(1)} MB/s`;
	return `${(bps / 1024 ** 3).toFixed(2)} GB/s`;
}

// Returns [scaledNumber, unitLabel, fractionDigits] for animating bps in
// the closest unit. Fraction digits chosen to keep the number stable as
// it grows within a unit window.
function scaleBps(bps: number): [number, string, number] {
	if (!Number.isFinite(bps) || bps < 0) return [0, 'B/s', 0];
	if (bps < 1024) return [bps, 'B/s', 0];
	if (bps < 1024 ** 2) return [bps / 1024, 'KB/s', 1];
	if (bps < 1024 ** 3) return [bps / 1024 ** 2, 'MB/s', 1];
	return [bps / 1024 ** 3, 'GB/s', 2];
}

function StatusIcon({ status }: { status: string }) {
	const tone = statusTone(status);
	const cls = `${tone} shrink-0`;
	switch (status) {
		case 'completed':
		case 'succeeded':
			return <Check className={cls} size={12} strokeWidth={2.5} />;
		case 'failed':
			return <X className={cls} size={12} strokeWidth={2.5} />;
		case 'partial':
		case 'cancelled':
			return <AlertTriangle className={cls} size={12} strokeWidth={2.5} />;
		case 'running':
			return <Loader2 className={`${cls} animate-spin`} size={12} strokeWidth={2.5} />;
		default:
			return <CircleDashed className={cls} size={12} strokeWidth={2.5} />;
	}
}

function TasksRibbon({ hostId, onJump }: { hostId: string; onJump: () => void }) {
	const q = useQuery<TasksPage>({
		queryKey: ['hosts', hostId, 'tasks'],
		queryFn: () => apiFetch<TasksPage>(`/v1/tasks?host_id=${encodeURIComponent(hostId)}&limit=10`),
		refetchInterval: 5_000,
	});
	const items = q.data?.items ?? [];

	return (
		<div className="flex flex-col">
			<RibbonHeader
				icon={Activity}
				title="Task History"
				count={items.length}
				onJump={onJump}
				tone="text-ok"
			/>
			<div className="mc-bezel flex-1 space-y-1 px-2 py-1.5 font-mono text-[11px]">
				{q.isLoading ? (
					<div className="text-text-dim">…syncing</div>
				) : items.length === 0 ? (
					<div className="text-text-dim">no active tasks</div>
				) : (
					items.slice(0, 4).map(t => (
						<div key={t.id} className="flex items-center gap-1.5" title={t.summary ?? t.kind}>
							<StatusIcon status={t.status} />
							<span className="min-w-0 flex-1 truncate text-text">{t.summary ?? t.kind}</span>
							<span className="shrink-0 text-text-dim">{relTime(t.created_at)}</span>
						</div>
					))
				)}
			</div>
		</div>
	);
}

function AuditRibbon({ hostId, onJump }: { hostId: string; onJump: () => void }) {
	const q = useQuery<AuditPage>({
		queryKey: ['hosts', hostId, 'audit'],
		queryFn: () => apiFetch<AuditPage>(`/v1/audit?subject=${encodeURIComponent(hostId)}&limit=10`),
		refetchInterval: 8_000,
	});
	const items = q.data?.items ?? [];

	return (
		<div className="flex flex-col">
			<RibbonHeader icon={ScrollText} title="Audit Trail" count={items.length} onJump={onJump} />
			<div className="mc-bezel flex-1 space-y-1 px-2 py-1.5 font-mono text-[11px]">
				{q.isLoading ? (
					<div className="text-text-dim">…syncing</div>
				) : items.length === 0 ? (
					<div className="text-text-dim">no entries</div>
				) : (
					items.slice(0, 4).map(e => (
						<div key={e.sequence} className="flex items-center gap-1.5 truncate">
							<span className="text-accent">#{e.sequence}</span>
							<span className="truncate text-text-dim">
								<span className="text-text">{e.actor}</span> {e.action}
							</span>
						</div>
					))
				)}
			</div>
		</div>
	);
}

function PostureRibbon({ hostId, onJump }: { hostId: string; onJump: () => void }) {
	const q = useQuery<PostureResponse>({
		queryKey: ['hosts', hostId, 'posture'],
		queryFn: () =>
			apiFetch<PostureResponse>(
				`/v1/posture?subject_kind=host&subject_id=${encodeURIComponent(hostId)}`,
			),
		refetchInterval: 15_000,
	});
	const items = q.data?.findings ?? [];

	return (
		<div className="flex flex-col">
			<RibbonHeader
				icon={AlertTriangle}
				title="Posture"
				count={items.length}
				onJump={onJump}
				tone={items.length > 0 ? 'text-warn' : 'text-ok'}
			/>
			<div className="mc-bezel flex-1 space-y-1 px-2 py-1.5 font-mono text-[11px]">
				{q.isLoading ? (
					<div className="text-text-dim">…scanning</div>
				) : items.length === 0 ? (
					<div className="text-ok">all clear</div>
				) : (
					items.slice(0, 4).map(f => (
						<div key={f.id} className="flex items-center gap-1.5 truncate">
							<span className={`mc-pip ${severityTone(f.severity)} border-current px-1 py-0`}>
								{f.severity.slice(0, 3).toUpperCase()}
							</span>
							<span className="truncate text-text">{f.title}</span>
						</div>
					))
				)}
			</div>
		</div>
	);
}

function AdvisoriesRibbon({ hostId, onJump }: { hostId: string; onJump: () => void }) {
	const q = useHostAdvisories(hostId, { status: 'open' });
	const items = q.data?.items ?? [];

	return (
		<div className="flex flex-col">
			<RibbonHeader
				icon={Activity}
				title="Advisories"
				count={items.length}
				onJump={onJump}
				tone={items.length > 0 ? 'text-danger' : 'text-ok'}
			/>
			<div className="mc-bezel flex-1 space-y-1 px-2 py-1.5 font-mono text-[11px]">
				{q.isLoading ? (
					<div className="text-text-dim">…loading</div>
				) : items.length === 0 ? (
					<div className="text-ok">no advisories</div>
				) : (
					items.slice(0, 4).map(a => (
						<div key={a.id} className="flex items-center gap-1.5 truncate">
							<span className={`mc-pip ${severityTone(a.severity)} border-current px-1 py-0`}>
								{a.severity.slice(0, 3).toUpperCase()}
							</span>
							<span className="truncate text-text">{a.package_name}</span>
						</div>
					))
				)}
			</div>
		</div>
	);
}

export function OverviewDashboard({ host, onJump }: Props) {
	const labels = host.labels ?? {};
	const labelEntries = Object.entries(labels);
	const lastSeen = host.last_seen_at ? parseServerTime(host.last_seen_at) : null;
	// Per-heartbeat token used by gauges to force delta re-evaluation when
	// values are flat — guarantees neutral rendering after a sample arrives
	// with no change.
	const tick = host.metrics_at ?? host.last_seen_at ?? undefined;
	const lastSeenAge = lastSeen ? Math.floor((Date.now() - lastSeen.getTime()) / 1000) : null;

	// Pull live values from heartbeat metrics + survey, falling back to the
	// legacy mock fields when the agent hasn't reported yet.
	const m = host.metrics;
	const s = host.survey;
	const memPct = m?.mem_used_pct ?? host.mem_pct;
	const diskPct = m?.disk_used_pct ?? host.disk_pct;
	const cpuPct = host.cpu_pct;
	const load1 = m?.load_1;
	const uptimeS = m?.uptime_seconds != null ? Number(m.uptime_seconds) : host.uptime_s;
	const netRxBps = m?.net_rx_bps != null ? Number(m.net_rx_bps) : null;
	const netTxBps = m?.net_tx_bps != null ? Number(m.net_tx_bps) : null;
	const osName = s?.os ?? host.os;
	const osVer = s?.os_version ?? host.os_version;
	const arch = s?.arch ?? host.arch;

	return (
		<div className="space-y-3">
			{/* Header band: hostname + status + last-seen */}
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="flex items-center gap-3">
					<Server className="text-accent" size={20} />
					<div className="leading-tight">
						<div className="font-mono text-[15px] font-semibold text-text">
							{host.display_name ?? host.hostname}
						</div>
						<div className="font-mono text-[10px] uppercase tracking-wider text-text-dim">
							{host.id.slice(0, 12)} · {osName ?? 'unknown'} {osVer ?? ''} · {arch ?? ''}
						</div>
					</div>
				</div>
				<div className="flex items-center gap-2">
					<StatusBeacon status={host.status} />
					{lastSeen ? (
						<span
							className="mc-pip border-hairline text-text-dim"
							title={lastSeen.toLocaleString()}
						>
							<span className="opacity-70">SEEN</span>
							<span className="text-text">
								{lastSeenAge != null ? fmtDuration(lastSeenAge) : '—'} ago
							</span>
						</span>
					) : null}
				</div>
			</div>

			{/* Telemetry gauge strip */}
			<div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-5">
				<Gauge
					icon={Cpu}
					iconTone="text-accent"
					label="LOAD 1m"
					value={
						load1 != null ? (
							<AnimNum
								value={load1}
								format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
							/>
						) : (
							<AnimNum value={cpuPct} suffix="%" format={{ maximumFractionDigits: 0 }} />
						)
					}
					pct={cpuPct}
					numeric={
						load1 != null
							? Math.round(load1 * 100) / 100
							: cpuPct != null
								? Math.round(cpuPct)
								: undefined
					}
					tick={tick}
					sub={
						s?.cpu_threads
							? `${s.cpu_cores ?? '?'}c/${s.cpu_threads}t`
							: undefined
					}
				/>
				<Gauge
					icon={MemoryStick}
					iconTone="text-warn"
					label="MEM"
					value={<AnimNum value={memPct} suffix="%" format={{ maximumFractionDigits: 0 }} />}
					pct={memPct}
					numeric={memPct != null ? Math.round(memPct) : undefined}
					tick={tick}
					sub={
						s?.mem_total_bytes
							? `${(Number(s.mem_total_bytes) / 1024 ** 3).toFixed(0)} GB`
							: undefined
					}
				/>
				<Gauge
					icon={HardDrive}
					iconTone="text-ok"
					label="DISK /"
					value={<AnimNum value={diskPct} suffix="%" format={{ maximumFractionDigits: 0 }} />}
					pct={diskPct}
					numeric={diskPct != null ? Math.round(diskPct) : undefined}
					tick={tick}
				/>
				<Gauge
					icon={Network}
					iconTone="text-accent"
					label="NET"
					value={(() => {
						if (netRxBps == null || netTxBps == null) return <span>—</span>;
						const [n, unit, frac] = scaleBps(netRxBps + netTxBps);
						return (
							<AnimNum
								value={n}
								suffix={` ${unit}`}
								format={{ minimumFractionDigits: frac, maximumFractionDigits: frac }}
							/>
						);
					})()}
					numeric={netRxBps != null && netTxBps != null ? netRxBps + netTxBps : undefined}
					// Bar fill uses sqrt-scaled mapping so kbps traffic is still
					// visible while the bar stays sub-50% for typical loads. 10 MB/s
					// reaches 100%. Linear would peg near 0% for kbps; full log
					// would over-amplify idle noise.
					pct={
						netRxBps != null && netTxBps != null
							? Math.min(100, Math.sqrt((netRxBps + netTxBps) / 10_000_000) * 100)
							: undefined
					}
					tick={tick}
					sub={
						netRxBps != null && netTxBps != null
							? `↓${fmtBps(netRxBps)} ↑${fmtBps(netTxBps)}`
							: 'rx/tx'
					}
				/>
				<Gauge
					icon={Timer}
					iconTone="text-text-dim"
					label="UPTIME"
					value={uptimeFmt(uptimeS)}
					neutral
				/>
			</div>

			{/* Identity / labels strip — kernel lives in the Hardware tab; this
				strip surfaces user-defined labels only to avoid duplicating the
				kernel string already shown in the header. */}
			<div className="mc-bezel flex flex-wrap items-center gap-1.5 px-2.5 py-1.5">
				<Fingerprint className="text-accent" size={11} />
				<span className="mc-heading">Labels</span>
				<div className="ml-auto flex flex-wrap gap-1">
					{labelEntries.length === 0 ? (
						<span className="mc-pip border-hairline text-text-dim">NO LABELS</span>
					) : (
						labelEntries.slice(0, 10).map(([k, v]) => {
							const tone = labelTone(k);
							return (
								<span key={k} className={`mc-pip ${tone}`}>
									<span className="opacity-60">{k.toUpperCase()}</span>
									<span className="text-text">{String(v)}</span>
								</span>
							);
						})
					)}
				</div>
			</div>

			{/* Four-column ribbon row */}
			<div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
				<TasksRibbon hostId={host.id} onJump={() => onJump('tasks')} />
				<PostureRibbon hostId={host.id} onJump={() => onJump('posture')} />
				<AuditRibbon hostId={host.id} onJump={() => onJump('audit')} />
				<AdvisoriesRibbon hostId={host.id} onJump={() => onJump('advisories')} />
			</div>
		</div>
	);
}
