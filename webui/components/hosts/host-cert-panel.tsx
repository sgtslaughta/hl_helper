'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { getHostCert, rotateCertNow, type HostCert } from '@/lib/api/hosts';
import { ReenrollModal } from '@/components/hosts/reenroll-modal';

const STATUS_COLOR: Record<HostCert['status'], string> = {
	healthy: 'text-emerald-400',
	rotating: 'text-amber-400',
	halted: 'text-red-500',
	expired: 'text-red-500',
};

const STATUS_DOT: Record<HostCert['status'], string> = {
	healthy: '●',
	rotating: '⚠',
	halted: '✕',
	expired: '✕',
};

function fmt(d: string | null): string {
	if (!d) return '—';
	return new Date(d).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC');
}

function relTime(d: string | null): string {
	if (!d) return '';
	const ms = new Date(d).getTime() - Date.now();
	const sec = Math.round(ms / 1000);
	const abs = Math.abs(sec);
	const past = sec < 0;
	let out: string;
	if (abs < 60) out = `${abs}s`;
	else if (abs < 3600) out = `${Math.round(abs / 60)}m`;
	else if (abs < 86400) out = `${Math.round(abs / 3600)}h`;
	else out = `${Math.round(abs / 86400)}d`;
	return past ? `${out} ago` : `in ${out}`;
}

export function HostCertPanel({ hostId }: { hostId: string }) {
	const qc = useQueryClient();
	const { data: cert, isLoading } = useQuery({
		queryKey: ['host-cert', hostId],
		queryFn: () => getHostCert(hostId),
		refetchInterval: 30_000,
	});
	const [reenrollOpen, setReenrollOpen] = useState(false);

	const rotateMut = useMutation({
		mutationFn: () => rotateCertNow(hostId),
		onSuccess: () => qc.invalidateQueries({ queryKey: ['host-cert', hostId] }),
	});

	if (isLoading || !cert) return <div className="text-sm text-zinc-500">Loading cert…</div>;

	const cooldownMs = cert.last_rotated_at
		? new Date(cert.last_rotated_at).getTime() + 60 * 60 * 1000 - Date.now()
		: 0;
	const inCooldown = cooldownMs > 0;

	return (
		<div className="rounded border border-zinc-800 bg-zinc-950 p-4 text-sm">
			<header className="mb-3 flex items-center justify-between">
				<h3 className="font-semibold">TLS Certificate</h3>
				<span className={STATUS_COLOR[cert.status]}>
					{STATUS_DOT[cert.status]} {cert.status[0].toUpperCase() + cert.status.slice(1)}
				</span>
			</header>

			<dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-zinc-300">
				<dt className="text-zinc-500">Serial</dt>
				<dd className="font-mono">
					{cert.serial ? `${cert.serial.slice(0, 8)}…${cert.serial.slice(-4)}` : '—'}
				</dd>

				<dt className="text-zinc-500">Issued</dt>
				<dd>{fmt(cert.issued_at)}</dd>

				<dt className="text-zinc-500">Expires</dt>
				<dd>
					{fmt(cert.expires_at)} <span className="text-zinc-500">({relTime(cert.expires_at)})</span>
				</dd>

				<dt className="text-zinc-500">Rotated</dt>
				<dd>
					{cert.rotation_count}× {cert.last_rotated_at && `(last ${fmt(cert.last_rotated_at)})`}
				</dd>
			</dl>

			<div className="mt-4 flex gap-2">
				<button
					type="button"
					disabled={inCooldown || rotateMut.isPending}
					onClick={() => rotateMut.mutate()}
					title={
						inCooldown ? `Cooldown: try again in ${Math.ceil(cooldownMs / 60000)} min` : undefined
					}
					className="rounded border border-zinc-700 px-3 py-1 hover:bg-zinc-800 disabled:opacity-40"
				>
					{rotateMut.isPending ? 'Rotating…' : 'Force rotate now'}
				</button>
				<button
					type="button"
					onClick={() => setReenrollOpen(true)}
					className="rounded border border-zinc-700 px-3 py-1 hover:bg-zinc-800"
				>
					Re-enroll host
				</button>
			</div>

			{reenrollOpen && (
				<ReenrollModal hostId={hostId} onClose={() => setReenrollOpen(false)} />
			)}
		</div>
	);
}
