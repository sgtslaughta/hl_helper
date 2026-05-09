'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Input } from '@/components/primitives/input';
import { Select } from '@/components/primitives/select';
import { FeedHealthCard } from '@/components/security/feed-health-card';
import { PostureFindingCard } from '@/components/security/posture-finding-card';
import { apiFetch } from '@/lib/api-client';
import { usePostureSummary } from '@/lib/api/advisories';
import { useCan } from '@/lib/rbac-helpers';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { useState } from 'react';

interface Finding {
	id: string;
	severity: string;
	title: string;
	summary: string;
	rule: string;
	subject_kind: string;
	subject_id: string | null;
	fix_action_url: string | null;
	suppressed_until: string | null;
}

interface PostureResponse {
	findings: Finding[];
}

export default function SecurityPage() {
	const [severityFilter, setSeverityFilter] = useState<string>('all');
	const [ruleSearch, setRuleSearch] = useState('');
	const canView = useCan('security:read');
	const postureSummary = usePostureSummary();

	const { data, isLoading } = useQuery<PostureResponse>({
		queryKey: ['posture', { severityFilter, ruleSearch }],
		queryFn: async () => {
			return await apiFetch('/v1/posture?include_suppressed=false');
		},
		enabled: canView,
	});

	if (!canView) {
		return (
			<EmptyState
				title="Access Denied"
				description="You don't have permission to view security posture"
				icon="🔒"
			/>
		);
	}

	const findings = data?.findings || [];

	const filtered = findings.filter(f => {
		if (severityFilter !== 'all' && f.severity !== severityFilter) {
			return false;
		}
		if (ruleSearch && !f.rule.toLowerCase().includes(ruleSearch.toLowerCase())) {
			return false;
		}
		return true;
	});

	const severityCounts = {
		critical: findings.filter(f => f.severity === 'critical').length,
		high: findings.filter(f => f.severity === 'high').length,
		medium: findings.filter(f => f.severity === 'medium').length,
		low: findings.filter(f => f.severity === 'low').length,
	};

	return (
		<div className="flex flex-col gap-6 p-6">
			<div>
				<h1 className="text-h1 text-text">Security Posture</h1>
				<p className="mt-2 text-text-dim">Fleet vulnerability and compliance findings</p>
			</div>

			<FeedHealthCard />

			{/* CVE Roll-up Section */}
			{postureSummary.isLoading ? (
				<div className="text-text-dim">Loading advisories summary...</div>
			) : postureSummary.isError ? (
				<div className="text-danger">Failed to load advisories summary</div>
			) : postureSummary.data ? (
				<div className="rounded border border-hairline bg-surface p-6">
					<div className="mb-4 flex items-center gap-2">
						<AlertTriangle className="h-5 w-5 text-danger" />
						<h2 className="text-h2 font-semibold text-text">CVE Summary</h2>
					</div>
					<div className="grid auto-cols-max gap-4 grid-flow-col">
						<div className="rounded border border-hairline bg-canvas p-4 text-center">
							<div className="text-2xl font-semibold text-danger">
								{postureSummary.data.totals.critical}
							</div>
							<div className="text-tiny text-text-dim">Critical</div>
						</div>
						<div className="rounded border border-hairline bg-canvas p-4 text-center">
							<div className="text-2xl font-semibold text-orange-400">
								{postureSummary.data.totals.high}
							</div>
							<div className="text-tiny text-text-dim">High</div>
						</div>
						<div className="rounded border border-hairline bg-canvas p-4 text-center">
							<div className="text-2xl font-semibold text-yellow-400">
								{postureSummary.data.totals.medium}
							</div>
							<div className="text-tiny text-text-dim">Medium</div>
						</div>
						<div className="rounded border border-hairline bg-canvas p-4 text-center">
							<div className="text-2xl font-semibold text-blue-400">
								{postureSummary.data.totals.low}
							</div>
							<div className="text-tiny text-text-dim">Low</div>
						</div>
						{postureSummary.data.kev_count > 0 && (
							<div className="rounded border border-danger/40 bg-danger/10 p-4 text-center">
								<div className="text-2xl font-semibold text-danger">
									{postureSummary.data.kev_count}
								</div>
								<div className="text-tiny text-danger">KEV</div>
							</div>
						)}
						{postureSummary.data.stale_update_hosts > 0 && (
							<div className="rounded border border-warn/40 bg-warn/10 p-4 text-center">
								<div className="text-2xl font-semibold text-warn">
									{postureSummary.data.stale_update_hosts}
								</div>
								<div className="text-tiny text-warn">Stale Updates</div>
							</div>
						)}
					</div>
				</div>
			) : null}

			<div className="grid auto-cols-max gap-4 grid-flow-col">
				<div className="rounded border border-hairline bg-surface p-4 text-center">
					<div className="text-2xl font-semibold text-danger">{severityCounts.critical}</div>
					<div className="text-tiny text-text-dim">Critical</div>
				</div>
				<div className="rounded border border-hairline bg-surface p-4 text-center">
					<div className="text-2xl font-semibold text-warn">{severityCounts.high}</div>
					<div className="text-tiny text-text-dim">High</div>
				</div>
				<div className="rounded border border-hairline bg-surface p-4 text-center">
					<div className="text-2xl font-semibold text-warn/70">{severityCounts.medium}</div>
					<div className="text-tiny text-text-dim">Medium</div>
				</div>
				<div className="rounded border border-hairline bg-surface p-4 text-center">
					<div className="text-2xl font-semibold text-ok">{severityCounts.low}</div>
					<div className="text-tiny text-text-dim">Low</div>
				</div>
			</div>

			<div className="flex gap-4">
				<Input
					placeholder="Search rules..."
					value={ruleSearch}
					onChange={e => setRuleSearch(e.target.value)}
				/>
				<Select
					value={severityFilter}
					onValueChange={setSeverityFilter}
					options={[
						{ value: 'all', label: 'All Severities' },
						{ value: 'critical', label: 'Critical' },
						{ value: 'high', label: 'High' },
						{ value: 'medium', label: 'Medium' },
						{ value: 'low', label: 'Low' },
					]}
				/>
			</div>

			{isLoading ? (
				<div className="text-center text-text-dim">Loading findings...</div>
			) : filtered.length === 0 ? (
				<EmptyState
					title="No findings"
					description={
						findings.length === 0 ? 'Your fleet is clean' : 'No findings match your filters'
					}
					icon={<ShieldCheck className="h-8 w-8 text-ok" />}
				/>
			) : (
				<div className="space-y-3">
					{filtered.map(f => (
						<PostureFindingCard
							key={f.id}
							id={f.id}
							severity={f.severity}
							title={f.title}
							summary={f.summary}
							rule={f.rule}
							subjectKind={f.subject_kind}
							subjectId={f.subject_id}
							fixActionUrl={f.fix_action_url}
							suppressedUntil={f.suppressed_until}
						/>
					))}
				</div>
			)}
		</div>
	);
}
