'use client';

import { apiFetch } from '@/lib/api-client';
import { useHostAdvisories } from '@/lib/api/advisories';
import { type Host, updateHeartbeatInterval } from '@/lib/api/hosts';
import { type HostRiskOut, useHostRisk, useRiskRecompute } from '@/lib/api/posture-risk';
import {
	type AuditUserLookup,
	auditActionHref,
	auditActorLabel,
	extractActorUserId,
	humanizeAuditAction,
} from '@/lib/audit-format';
import { fmtDuration, parseServerTime, relTime } from '@/lib/time';
import NumberFlow, { type Format as NumberFlowFormat } from '@number-flow/react';
import * as Popover from '@radix-ui/react-popover';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
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
	RotateCw,
	ScrollText,
	Server,
	Timer,
	TrendingDown,
	TrendingUp,
	X,
} from 'lucide-react';
import Link from 'next/link';
import { type ComponentType, type ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { RiskHoverPanel } from './risk-hover-panel';

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
function useSamples(
	value: number | undefined,
	tick: string | number | undefined,
	max = 60,
): number[] {
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
	staticTraceColor,
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
	// Override the auto slope-based sparkline color with a constant CSS
	// color (e.g. NET should always be neon blue regardless of trend).
	staticTraceColor?: string;
}) {
	const sign = useDeltaSign(numeric ?? pct, tick);
	const valueTone = neutral ? 'text-text' : deltaTone(sign);
	const samples = useSamples(numeric ?? pct, tick);
	// Trend tone: compare the average of the early window to the late
	// window across the full buffer. Picks status color from the slope
	// rather than the absolute pct, so a calm-but-rising metric goes
	// red even before it crosses 75% / 90% thresholds.
	const trendTone = neutral ? undefined : (staticTraceColor ?? trendStatusVar(samples));
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
				<div
					className={`mc-readout flex items-center gap-1 text-[15px] font-semibold ${valueTone}`}
				>
					{typeof value === 'string' || typeof value === 'number' ? <span>{value}</span> : value}
					{neutral ? null : <DeltaArrow sign={sign} />}
				</div>
				{sub ? (
					<div className="font-mono text-[9px] uppercase tracking-wider text-text-dim">{sub}</div>
				) : null}
			</div>
			{!neutral && trendTone ? <Sparkline values={samples} color={trendTone} /> : null}
		</div>
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

function HostHealthCluster({
	host,
	lastSeenAge,
}: {
	host: Host;
	lastSeenAge: number | null;
}) {
	const lastSeen = host.last_seen_at ? parseServerTime(host.last_seen_at) : null;
	const interval = host.heartbeat_interval_s ?? 60;
	const [open, setOpen] = useState(false);
	const [draft, setDraft] = useState<number>(interval);
	const [saved, setSaved] = useState(false);
	const qc = useQueryClient();
	const mut = useMutation({
		mutationFn: (s: number) => updateHeartbeatInterval(host.id, s),
		onSuccess: () => {
			setSaved(true);
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
			setTimeout(() => setSaved(false), 1800);
		},
	});

	useEffect(() => {
		if (open) setDraft(interval);
	}, [open, interval]);

	// Heartbeat freshness: green if last_seen within 2x interval, warn within 4x, danger beyond.
	const ageS = lastSeenAge ?? Number.POSITIVE_INFINITY;
	const tone = ageS < interval * 2 ? 'text-ok' : ageS < interval * 4 ? 'text-warn' : 'text-danger';

	const statusToneMap: Record<string, string> = {
		healthy: 'text-ok',
		online: 'text-ok',
		warning: 'text-warn',
		critical: 'text-danger',
		offline: 'text-text-dim',
		pending: 'text-accent',
		revoked: 'text-danger',
	};
	const statusTone = statusToneMap[host.status] ?? 'text-text-dim';
	const statusPulse = host.status === 'healthy';
	const triggerTitle = 'Click for heartbeat settings';

	return (
		<Popover.Root open={open} onOpenChange={setOpen}>
			<Popover.Anchor asChild>
				<div className="flex items-center gap-2">
					<button
						type="button"
						onClick={() => setOpen(true)}
						className={`mc-pip ${statusTone} border-current hover:bg-surface-2`}
						title={triggerTitle}
						aria-label={`Agent health: ${host.status}. ${triggerTitle}`}
					>
						<span className={`mc-led ${statusPulse ? 'mc-led-pulse' : ''}`} />
						{host.status.toUpperCase()}
					</button>
					<button
						type="button"
						onClick={() => setOpen(true)}
						className={`mc-pip border-hairline ${tone} hover:bg-surface-2`}
						title={lastSeen ? `${lastSeen.toLocaleString()} · ${triggerTitle}` : triggerTitle}
					>
						<span className="opacity-70">SEEN</span>
						<span className="text-text">
							{lastSeenAge != null ? `${fmtDuration(lastSeenAge)} ago` : 'never'}
						</span>
					</button>
				</div>
			</Popover.Anchor>
			<Popover.Portal>
				<Popover.Content
					side="bottom"
					align="end"
					sideOffset={6}
					className="z-[100] w-72 rounded border border-hairline bg-surface p-3 font-mono text-[11px] shadow-xl"
				>
					<div className="mb-2 flex items-center justify-between">
						<span className="mc-heading">Heartbeat</span>
						<span className={`mc-pip border-current px-1 py-0 ${tone}`}>
							{tone === 'text-ok' ? 'OK' : tone === 'text-warn' ? 'STALE' : 'OFFLINE'}
						</span>
					</div>
					<dl className="space-y-1 border-b border-hairline pb-2 text-text-dim">
						<div className="flex justify-between">
							<dt>Last seen</dt>
							<dd className="text-text" title={lastSeen ? lastSeen.toLocaleString() : ''}>
								{lastSeen ? `${fmtDuration(ageS)} ago` : 'never'}
							</dd>
						</div>
						<div className="flex justify-between">
							<dt>Current interval</dt>
							<dd className="text-text">{interval}s</dd>
						</div>
						<div className="flex justify-between">
							<dt>Next expected</dt>
							<dd className="text-text">
								{lastSeen ? fmtDuration(Math.max(0, interval - ageS)) : '—'}
							</dd>
						</div>
					</dl>
					<label className="mt-2 block">
						<div className="uppercase tracking-[0.14em] text-text-dim">Update interval (sec)</div>
						<div className="mt-1 flex gap-1.5">
							<input
								type="number"
								min={5}
								max={3600}
								value={draft}
								onChange={e => setDraft(Number(e.target.value))}
								className="w-24 rounded-sm border border-hairline bg-bezel/60 px-2 py-1 text-right text-[12px] text-text outline-none focus:border-accent"
								aria-label="Heartbeat interval"
							/>
							<button
								type="button"
								onClick={() => {
									if (draft >= 5 && draft <= 3600 && draft !== interval) mut.mutate(draft);
								}}
								disabled={mut.isPending || draft < 5 || draft > 3600 || draft === interval}
								className="rounded-sm border border-hairline bg-accent/10 px-2 py-1 text-accent hover:bg-accent/20 disabled:opacity-40"
							>
								{mut.isPending ? '…' : 'Save'}
							</button>
							{saved && <span className="ml-auto flex items-center text-ok">Saved</span>}
						</div>
						<div className="mt-1 text-[9px] text-text-dim">Range: 5–3600 sec</div>
					</label>
				</Popover.Content>
			</Popover.Portal>
		</Popover.Root>
	);
}

interface SeverityBuckets {
	critical: number;
	high: number;
	medium: number;
	low: number;
	unknown: number;
}

function bucketSeverities(items: { severity: string }[]): SeverityBuckets {
	const out: SeverityBuckets = { critical: 0, high: 0, medium: 0, low: 0, unknown: 0 };
	for (const it of items) {
		const k = it.severity.toLowerCase();
		if (k === 'critical') out.critical++;
		else if (k === 'high') out.high++;
		else if (k === 'medium') out.medium++;
		else if (k === 'low') out.low++;
		else out.unknown++;
	}
	return out;
}

interface PieSlice {
	key: keyof SeverityBuckets;
	label: string; // 2-char abbrev
	full: string; // full name
	count: number;
	color: string; // CSS var
}

function SeverityPie({
	buckets,
	hostId,
	size = 120,
}: {
	buckets: SeverityBuckets;
	hostId: string;
	size?: number;
}) {
	const navigate = (sev: string) => {
		if (typeof window === 'undefined') return;
		window.location.href = `/advisories?host_id=${encodeURIComponent(hostId)}&severity=${sev}`;
	};
	const slicesAll: PieSlice[] = [
		{
			key: 'critical',
			label: 'CR',
			full: 'critical',
			count: buckets.critical,
			color: 'var(--color-danger)',
		},
		{
			key: 'high',
			label: 'HI',
			full: 'high',
			count: buckets.high,
			color: 'var(--color-danger)',
		},
		{
			key: 'medium',
			label: 'MD',
			full: 'medium',
			count: buckets.medium,
			color: 'var(--color-warn)',
		},
		{ key: 'low', label: 'LO', full: 'low', count: buckets.low, color: 'var(--color-accent)' },
		{
			key: 'unknown',
			label: 'UNK',
			full: 'unknown',
			count: buckets.unknown,
			color: 'var(--color-text-dim)',
		},
	];
	const slices = slicesAll.filter(s => s.count > 0);
	const total = slices.reduce((a, s) => a + s.count, 0);
	const [hover, setHover] = useState<string | null>(null);
	const cx = size / 2;
	const cy = size / 2;
	const r = size / 2 - 2;
	const innerR = r * 0.55;

	if (total === 0) {
		return (
			<div
				className="flex items-center justify-center text-ok font-mono text-[11px]"
				style={{ height: size }}
			>
				no advisories
			</div>
		);
	}

	// Build SVG arc paths.
	let acc = 0;
	const paths = slices.map(s => {
		const startA = (acc / total) * Math.PI * 2 - Math.PI / 2;
		acc += s.count;
		const endA = (acc / total) * Math.PI * 2 - Math.PI / 2;
		const large = s.count / total > 0.5 ? 1 : 0;
		const x1 = cx + r * Math.cos(startA);
		const y1 = cy + r * Math.sin(startA);
		const x2 = cx + r * Math.cos(endA);
		const y2 = cy + r * Math.sin(endA);
		const xi2 = cx + innerR * Math.cos(endA);
		const yi2 = cy + innerR * Math.sin(endA);
		const xi1 = cx + innerR * Math.cos(startA);
		const yi1 = cy + innerR * Math.sin(startA);
		const d = [
			`M ${x1} ${y1}`,
			`A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`,
			`L ${xi2} ${yi2}`,
			`A ${innerR} ${innerR} 0 ${large} 0 ${xi1} ${yi1}`,
			'Z',
		].join(' ');
		return { slice: s, d };
	});

	const hovered = slices.find(s => s.key === hover) ?? null;

	return (
		<div className="flex items-center gap-3 px-2 py-2">
			<div className="relative shrink-0" style={{ width: size, height: size }}>
				<svg width={size} height={size} role="img" aria-label="Severity distribution">
					<title>Advisory severity distribution</title>
					{paths.map(({ slice, d }) => {
						const isHover = hover === slice.key;
						return (
							<path
								key={slice.key}
								d={d}
								fill={slice.color}
								fillOpacity={hover && !isHover ? 0.35 : 0.8}
								stroke="var(--color-bezel)"
								strokeWidth={1}
								style={{
									filter: isHover ? 'brightness(1.4) drop-shadow(0 0 6px currentColor)' : undefined,
									color: slice.color,
									transition: 'fill-opacity 120ms, filter 120ms',
									cursor: 'pointer',
								}}
								onMouseEnter={() => setHover(slice.key)}
								onMouseLeave={() => setHover(null)}
								onClick={() => navigate(slice.full)}
								role="button"
								tabIndex={0}
								onKeyDown={ev => {
									if (ev.key === 'Enter' || ev.key === ' ') {
										ev.preventDefault();
										navigate(slice.full);
									}
								}}
								aria-label={`${slice.count} ${slice.full} advisories — click to filter`}
							/>
						);
					})}
				</svg>
				{/* Center readout */}
				<div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center font-mono leading-none">
					<span className="text-[16px] font-semibold text-text">
						{hovered ? hovered.count : total}
					</span>
					<span className="text-[8px] uppercase tracking-wider text-text-dim mt-0.5">
						{hovered ? hovered.full : 'total'}
					</span>
				</div>
			</div>
			{/* Legend */}
			<div className="flex flex-1 flex-col gap-0.5 text-[11px]">
				{slices.map(s => (
					<button
						type="button"
						key={s.key}
						onMouseEnter={() => setHover(s.key)}
						onMouseLeave={() => setHover(null)}
						onClick={() => navigate(s.full)}
						className={`flex items-center gap-1.5 rounded px-1 py-0.5 text-left hover:bg-surface-2 ${
							hover === s.key ? 'bg-surface-2' : ''
						}`}
					>
						<span className="h-2 w-2 rounded-sm shrink-0" style={{ backgroundColor: s.color }} />
						<span className="text-text-dim uppercase tracking-wider w-7">{s.label}</span>
						<span className="text-text font-mono">{s.count}</span>
						<span className="ml-auto text-text-dim/60 font-mono">
							{((s.count / total) * 100).toFixed(0)}%
						</span>
					</button>
				))}
			</div>
		</div>
	);
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
	const previewItems = items.slice(0, 4);

	const userIds = Array.from(
		new Set(previewItems.map(e => extractActorUserId(e.actor)).filter((x): x is string => !!x)),
	);
	const userQs = useQueries({
		queries: userIds.map(id => ({
			queryKey: ['users', id],
			queryFn: () =>
				apiFetch<AuditUserLookup>(`/v1/users/${id}`).catch(() => ({ id }) as AuditUserLookup),
			staleTime: 5 * 60_000,
		})),
	});
	const userMap: Record<string, AuditUserLookup | undefined> = {};
	userIds.forEach((id, i) => {
		userMap[id] = userQs[i]?.data;
	});

	return (
		<div className="flex flex-col">
			<RibbonHeader icon={ScrollText} title="Audit Trail" count={items.length} onJump={onJump} />
			<div className="mc-bezel flex-1 space-y-1 px-2 py-1.5 font-mono text-[11px]">
				{q.isLoading ? (
					<div className="text-text-dim">…syncing</div>
				) : items.length === 0 ? (
					<div className="text-text-dim">no entries</div>
				) : (
					previewItems.map(e => {
						const href = auditActionHref(e.action, e.payload);
						const ts = relTime(e.timestamp);
						const actor = auditActorLabel(e.actor, userMap);
						const verb = humanizeAuditAction(e.action);
						const ttl = `${new Date(e.timestamp).toLocaleString()} · ${e.action}`;
						const cls = 'flex items-center gap-1.5 truncate px-1 -mx-1 rounded-sm';
						return href ? (
							<Link
								key={e.sequence}
								href={href}
								onClick={ev => ev.stopPropagation()}
								className={`${cls} hover:bg-surface-2`}
								title={`${ttl} · open detail`}
							>
								<span className="text-text-dim/60 shrink-0">{ts}</span>
								<span className="truncate text-text-dim">
									<span className="text-text">{actor}</span>{' '}
									<span className="text-accent">{verb}</span>
								</span>
							</Link>
						) : (
							<div key={e.sequence} className={cls} title={ttl}>
								<span className="text-text-dim/60 shrink-0">{ts}</span>
								<span className="truncate text-text-dim">
									<span className="text-text">{actor}</span> {verb}
								</span>
							</div>
						);
					})
				)}
			</div>
		</div>
	);
}

const RISK_DISCLAIMER =
	'Risk score is heuristic. It uses only advisory severity + CISA KEV + EPSS — it does not see your firewall, network exposure, EDR/AV, segmentation, runtime mitigations, or compensating controls. A "severe" score may be benign behind defenses; a "stable" score may still hide blast radius. Use as a triage hint, not a verdict.';

function RiskInfographic({
	risk,
	hostId,
	loading,
}: {
	risk: HostRiskOut;
	hostId: string;
	loading: boolean;
}) {
	const LEVEL_COLOR: Record<string, string> = {
		minimal: 'var(--color-ok)',
		stable: 'var(--color-ok)',
		moderate: 'var(--color-accent)',
		elevated: 'var(--color-warn)',
		high: '#ff8400',
		severe: 'var(--color-danger)',
		unknown: 'var(--color-text-dim)',
	};
	const color = LEVEL_COLOR[risk.level] ?? 'var(--color-text-dim)';

	const LEVEL_LABEL: Record<string, string> = {
		minimal: 'All clear',
		stable: 'Stable — monitor',
		moderate: 'Moderate — review',
		elevated: 'Elevated — patch this week',
		high: 'High — patch now',
		severe: 'Severe — under active risk',
		unknown: 'Insufficient signal — scan host',
	};
	const label = LEVEL_LABEL[risk.level] ?? risk.level;

	const kevCount = 0; // not exposed by API yet — see follow-up task
	const maxEpss = 0;
	const criticalCount = 0;
	const highCount = 0;

	// Compact half-circle gauge. Tighter aspect ratio than the original
	// design so the ribbon doesn't dominate the overview vertically.
	const W = 220;
	const H = 88;
	const cx = W / 2;
	const cy = H - 4;
	const r = 72;

	// Helper: polar→cartesian for our half-circle (angle in degrees, 180=left)
	const polar = (angDeg: number) => {
		const a = (angDeg * Math.PI) / 180;
		return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
	};

	// Risk gauge is split into colored bands matching level thresholds.
	const bands = [
		{ from: 0, to: 20, color: 'var(--color-ok)' },
		{ from: 20, to: 40, color: 'var(--color-accent)' },
		{ from: 40, to: 65, color: 'var(--color-warn)' },
		{ from: 65, to: 85, color: '#ff8400' },
		{ from: 85, to: 100, color: 'var(--color-danger)' },
	];

	const scoreToAngle = (s: number) => 180 + (Math.min(100, Math.max(0, s)) / 100) * 180;

	const arcPath = (fromScore: number, toScore: number) => {
		const a1 = scoreToAngle(fromScore);
		const a2 = scoreToAngle(toScore);
		const [x1, y1] = polar(a1);
		const [x2, y2] = polar(a2);
		const large = a2 - a1 > 180 ? 1 : 0;
		return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
	};

	// Animate score 0 → actual on first paint and on subsequent changes.
	// `displayScoreRef` snapshots the running value so re-running the
	// animation when target changes doesn't add `displayScore` to the dep
	// list (which would re-trigger every frame and break easing).
	const [displayScore, setDisplayScore] = useState(0);
	const displayScoreRef = useRef(0);
	useEffect(() => {
		displayScoreRef.current = displayScore;
	}, [displayScore]);
	useEffect(() => {
		if (loading) return;
		const target = risk.score ?? 0;
		const start = performance.now();
		const from = displayScoreRef.current;
		const dur = 700; // ms
		let raf = 0;
		const tick = (t: number) => {
			const p = Math.min(1, (t - start) / dur);
			const eased = 1 - (1 - p) ** 3; // easeOutCubic
			const v = from + (target - from) * eased;
			setDisplayScore(v);
			if (p < 1) raf = requestAnimationFrame(tick);
		};
		raf = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(raf);
	}, [risk.score, loading]);

	const needleAngle = scoreToAngle(displayScore);
	const [nx, ny] = polar(needleAngle);

	// Mouse-tracked hover panel for top drivers. Rendered via portal so it
	// escapes the ribbon's overflow clipping and sits at the topmost layer.
	const [hovered, setHovered] = useState(false);
	const [mouse, setMouse] = useState({ x: 0, y: 0 });
	// Disclaimer popover open state — when true, suppress the hover panel
	// so the two layers don't fight for attention.
	const [disclaimerOpen, setDisclaimerOpen] = useState(false);
	const recompute = useRiskRecompute();
	const containerRef = useRef<HTMLDivElement | null>(null);
	const handleMove = (e: React.MouseEvent) => {
		setMouse({ x: e.clientX, y: e.clientY });
	};

	// Derive score display — null becomes 0 for display purposes
	const displayedScore = risk.score ?? 0;

	const PANEL_W = 260;
	const PANEL_OFFSET = 14;
	// Clamp to viewport. Prefer right of cursor, fall back to left when
	// the panel would clip the right edge.
	let panelLeft = mouse.x + PANEL_OFFSET;
	if (typeof window !== 'undefined' && panelLeft + PANEL_W > window.innerWidth - 8) {
		panelLeft = mouse.x - PANEL_W - PANEL_OFFSET;
	}
	let panelTop = mouse.y + PANEL_OFFSET;
	if (typeof window !== 'undefined' && panelTop + 200 > window.innerHeight - 8) {
		panelTop = Math.max(8, window.innerHeight - 220);
	}

	return (
		<div
			ref={containerRef}
			className="relative cursor-pointer px-2 pt-1.5 pb-1"
			onMouseEnter={() => setHovered(true)}
			onMouseLeave={() => setHovered(false)}
			onMouseMove={handleMove}
			onClick={e => {
				// Don't navigate if the click was on the disclaimer ⓘ button
				// or its popover content.
				const t = e.target as HTMLElement;
				if (t.closest('[data-radix-popover-trigger], [data-radix-popover-content]')) return;
				if (typeof window !== 'undefined') {
					window.location.href = `/advisories?host_id=${encodeURIComponent(hostId)}`;
				}
			}}
			onKeyDown={e => {
				if (e.key === 'Enter' || e.key === ' ') {
					e.preventDefault();
					if (typeof window !== 'undefined') {
						window.location.href = `/advisories?host_id=${encodeURIComponent(hostId)}`;
					}
				}
			}}
			// biome-ignore lint/a11y/useSemanticElements: contains nested Radix Popover.Trigger button — nesting <button> in <button> is invalid HTML
			role="button"
			tabIndex={0}
			aria-label={`Open advisories for this host — risk ${displayedScore} of 100, ${label}`}
		>
			{/* Recompute button — sits left of the disclaimer ⓘ. Stops click
			    propagation so the gauge's parent onClick (open advisories)
			    doesn't fire. */}
			<button
				type="button"
				onClick={ev => {
					ev.stopPropagation();
					recompute.mutate(hostId);
				}}
				disabled={recompute.isPending}
				title="Recompute risk score now"
				aria-label="Recompute risk score"
				className="absolute right-7 top-0.5 z-10 flex h-6 w-6 items-center justify-center rounded text-text-dim hover:bg-surface-2 hover:text-text disabled:opacity-50"
			>
				<RotateCw size={11} className={recompute.isPending ? 'animate-spin' : ''} />
			</button>

			{/* Disclaimer popover — click ⓘ to open. Bigger hit-target than a
			    title-attr-only tooltip; persists until dismissed. */}
			<Popover.Root open={disclaimerOpen} onOpenChange={setDisclaimerOpen}>
				<Popover.Trigger asChild>
					<button
						type="button"
						className="absolute right-1 top-0.5 z-10 flex h-6 w-6 items-center justify-center rounded text-text-dim hover:bg-surface-2 hover:text-text"
						aria-label="About this risk score"
					>
						<svg
							width="13"
							height="13"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							strokeWidth="2"
							strokeLinecap="round"
							strokeLinejoin="round"
							aria-hidden="true"
						>
							<title>About this risk score</title>
							<circle cx="12" cy="12" r="10" />
							<path d="M12 16v-4" />
							<path d="M12 8h.01" />
						</svg>
					</button>
				</Popover.Trigger>
				<Popover.Portal>
					<Popover.Content
						side="bottom"
						align="end"
						sideOffset={6}
						collisionPadding={12}
						className="z-[9999] w-[320px] rounded border border-hairline bg-surface p-3 font-mono text-[11px] text-text shadow-2xl"
					>
						<div className="mb-1.5 flex items-center justify-between">
							<span className="text-[10px] uppercase tracking-[0.18em] text-warn">
								⚠ Heuristic — not a verdict
							</span>
							<Popover.Close asChild>
								<button
									type="button"
									aria-label="Close"
									className="rounded px-1 text-text-dim hover:bg-surface-2 hover:text-text"
								>
									✕
								</button>
							</Popover.Close>
						</div>
						<p className="text-text-dim leading-relaxed">{RISK_DISCLAIMER}</p>
						<div className="mt-2 border-t border-hairline pt-2 text-[10px] text-text-dim/80">
							<div className="mb-1 uppercase tracking-wider">Inputs used</div>
							<ul className="list-disc pl-4 space-y-0.5">
								<li>Advisory severity (critical/high/medium/low)</li>
								<li>CISA KEV (active in wild)</li>
								<li>EPSS 30-day exploitation probability</li>
							</ul>
							<div className="mt-1.5 mb-1 uppercase tracking-wider">Not modeled</div>
							<ul className="list-disc pl-4 space-y-0.5">
								<li>Network exposure / segmentation / firewall</li>
								<li>EDR / AV / runtime mitigations</li>
								<li>Reachability of the vulnerable code path</li>
								<li>Compensating controls in place</li>
							</ul>
						</div>
					</Popover.Content>
				</Popover.Portal>
			</Popover.Root>

			<div className="relative">
				<svg
					width="100%"
					viewBox={`0 0 ${W} ${H}`}
					role="img"
					aria-label={`Risk gauge: ${displayedScore} of 100 — ${label}`}
					style={{ overflow: 'visible', display: 'block' }}
				>
					<title>Risk gauge — heuristic</title>
					{bands.map(b => (
						<path
							key={`${b.from}-${b.to}`}
							d={arcPath(b.from, b.to)}
							stroke={b.color}
							strokeOpacity={loading ? 0.15 : 0.35}
							strokeWidth={9}
							fill="none"
							strokeLinecap="butt"
						/>
					))}
					{!loading && displayScore > 0 ? (
						<path
							d={arcPath(0, displayScore)}
							stroke={color}
							strokeWidth={9}
							fill="none"
							strokeLinecap="round"
							style={{ filter: `drop-shadow(0 0 5px ${color})` }}
						/>
					) : null}
					{!loading ? (
						<>
							<line
								x1={cx}
								y1={cy}
								x2={nx}
								y2={ny}
								stroke={color}
								strokeWidth={2}
								strokeLinecap="round"
							/>
							<circle cx={cx} cy={cy} r={3} fill={color} />
						</>
					) : null}
				</svg>
				<div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center font-mono leading-none">
					<span
						className="text-[20px] font-semibold tabular-nums"
						style={{ color: loading ? 'var(--color-text-dim)' : color }}
					>
						{loading ? '…' : Math.round(displayScore)}
					</span>
				</div>
			</div>

			{/* Label gets its own row so long labels ("Severe — under active risk")
			    aren't truncated by the chip cluster. */}
			<div className="mt-1 text-center">
				<span className="font-mono text-[10px] uppercase tracking-wider" style={{ color }}>
					{label}
				</span>
			</div>
			<div className="mt-1 flex items-center justify-center gap-1 font-mono text-[9px]">
				<MiniChip
					label="KEV"
					value={kevCount}
					tone={kevCount > 0 ? 'text-danger' : 'text-text-dim'}
				/>
				<MiniChip
					label="EPSS"
					value={maxEpss > 0 ? `${(maxEpss * 100).toFixed(0)}%` : '—'}
					tone={maxEpss > 0.5 ? 'text-danger' : maxEpss > 0.1 ? 'text-warn' : 'text-text-dim'}
				/>
				<MiniChip
					label="C/H"
					value={`${criticalCount}/${highCount}`}
					tone={criticalCount > 0 ? 'text-danger' : highCount > 0 ? 'text-warn' : 'text-text-dim'}
				/>
			</div>

			<a className="sr-only" href={`/advisories?host_id=${encodeURIComponent(hostId)}`}>
				Open advisories for this host
			</a>

			{/* Mouse-tracked hover panel — portaled to body so it sits above
			    every ribbon/grid clip. Pointer-events-none so cursor motion
			    doesn't bounce between trigger + panel. */}
			{typeof document !== 'undefined' && hovered && !disclaimerOpen
				? createPortal(
						<div
							className="pointer-events-none fixed rounded border border-hairline bg-surface p-2 shadow-2xl"
							style={{
								left: panelLeft,
								top: panelTop,
								width: PANEL_W,
								zIndex: 9999,
							}}
						>
							<RiskHoverPanel risk={risk} />
						</div>,
						document.body,
					)
				: null}
		</div>
	);
}

function MiniChip({
	label,
	value,
	tone,
	title,
}: {
	label: string;
	value: number | string;
	tone: string;
	title?: string;
}) {
	return (
		<span
			className={`inline-flex items-center gap-0.5 rounded-sm border border-hairline px-1 py-0 leading-none ${tone}`}
			title={title}
		>
			<span className="opacity-60">{label}</span>
			<span className="font-semibold">{value}</span>
		</span>
	);
}

function PostureRibbon({ hostId, onJump }: { hostId: string; onJump: () => void }) {
	const q = useHostRisk(hostId);
	const data = q.data;

	const tone =
		!data || data.score == null
			? 'text-text-dim'
			: data.score > 65
				? 'text-danger'
				: data.score > 40
					? 'text-warn'
					: data.score > 0
						? 'text-accent'
						: 'text-ok';

	return (
		<div className="flex flex-col">
			<RibbonHeader
				icon={AlertTriangle}
				title="Posture"
				count={data?.score ?? 0}
				onJump={onJump}
				tone={tone}
			/>
			<div className="mc-bezel flex flex-1 flex-col font-mono text-[11px]">
				{q.isLoading || !data ? (
					<div className="px-2 py-2 text-text-dim">…loading</div>
				) : (
					<RiskInfographic risk={data} hostId={hostId} loading={false} />
				)}
			</div>
		</div>
	);
}

function AdvisoriesRibbon({ hostId, onJump }: { hostId: string; onJump: () => void }) {
	const q = useHostAdvisories(hostId, { status: 'open' });
	const items = q.data?.items ?? [];
	const buckets = bucketSeverities(items);
	const worstTone =
		buckets.critical > 0 || buckets.high > 0
			? 'text-danger'
			: buckets.medium > 0
				? 'text-warn'
				: items.length > 0
					? 'text-accent'
					: 'text-ok';

	return (
		<div className="flex flex-col">
			<RibbonHeader
				icon={Activity}
				title="Advisories"
				count={items.length}
				onJump={onJump}
				tone={worstTone}
			/>
			<div className="mc-bezel flex flex-1 flex-col font-mono text-[11px]">
				{q.isLoading ? (
					<div className="px-2 py-2 text-text-dim">…loading</div>
				) : (
					<SeverityPie buckets={buckets} hostId={hostId} />
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
				<HostHealthCluster host={host} lastSeenAge={lastSeenAge} />
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
					sub={s?.cpu_threads ? `${s.cpu_cores ?? '?'}c/${s.cpu_threads}t` : undefined}
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
					// NET trace stays neon blue regardless of trend slope —
					// reads as "throughput" not "alert" since spikes here are normal.
					staticTraceColor="var(--color-accent)"
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
