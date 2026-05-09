import { apiFetch } from '@/lib/api-client';
import {
	useInfiniteQuery,
	useMutation,
	useQuery,
	useQueryClient,
	type UseInfiniteQueryResult,
	type UseMutationResult,
	type UseQueryResult,
} from '@tanstack/react-query';

export interface AffectedPackage {
	name: string;
	current_version: string;
	fixed_version: string | null;
}

export interface Advisory {
	id: string;
	severity: string;
	title: string;
	summary: string;
	epss: number;
	kev: boolean;
	published_at: string;
	cve_id: string;
}

export interface AdvisoryDetail extends Advisory {
	affected_packages: AffectedPackage[];
}

export interface HostAdvisory {
	id: string;
	host_id: string;
	advisory_id: string;
	status: 'open' | 'suppressed' | 'fixed';
	severity: string;
	package_name: string;
	current_version: string;
	fixed_version: string | null;
	epss: number;
	kev: boolean;
	suppressed_until: string | null;
	suppressed_reason: string | null;
	created_at: string;
	updated_at: string;
}

export interface PostureSummary {
	totals: {
		critical: number;
		high: number;
		medium: number;
		low: number;
	};
	kev_count: number;
	stale_update_hosts: number;
	feed_sources: string[];
}

export interface AdvisoriesResponse {
	items: Advisory[];
	next_cursor: string | null;
}

export interface HostAdvisoriesResponse {
	items: HostAdvisory[];
	next_cursor: string | null;
}

export function useAdvisories(opts?: {
	severity?: string;
	kev?: boolean;
	minEpss?: number;
}): UseInfiniteQueryResult<AdvisoriesResponse> {
	return useInfiniteQuery({
		queryKey: ['advisories', opts],
		queryFn: async ({ pageParam }) => {
			const params = new URLSearchParams();
			if (opts?.severity) params.set('severity', opts.severity);
			if (opts?.kev) params.set('kev', 'true');
			if (opts?.minEpss !== undefined) params.set('min_epss', String(opts.minEpss));
			if (pageParam) params.set('cursor', pageParam);
			params.set('limit', '20');

			const qs = params.toString();
			return apiFetch<AdvisoriesResponse>(
				`/v1/advisories${qs ? `?${qs}` : ''}`,
			);
		},
		initialPageParam: null as string | null,
		getNextPageParam: (lastPage) => lastPage.next_cursor,
	});
}

export function useAdvisory(id: string): UseQueryResult<AdvisoryDetail> {
	return useQuery({
		queryKey: ['advisories', id],
		queryFn: () => apiFetch<AdvisoryDetail>(`/v1/advisories/${encodeURIComponent(id)}`),
	});
}

export function useHostAdvisories(
	hostId: string,
	opts?: { status?: string; severity?: string },
): UseQueryResult<HostAdvisoriesResponse> {
	return useQuery({
		queryKey: ['hosts', hostId, 'advisories', opts],
		queryFn: async () => {
			const params = new URLSearchParams();
			if (opts?.status) params.set('status', opts.status);
			if (opts?.severity) params.set('severity', opts.severity);

			const qs = params.toString();
			return apiFetch<HostAdvisoriesResponse>(
				`/v1/hosts/${encodeURIComponent(hostId)}/advisories${qs ? `?${qs}` : ''}`,
			);
		},
	});
}

export function usePostureSummary(): UseQueryResult<PostureSummary> {
	return useQuery({
		queryKey: ['posture', 'summary'],
		queryFn: () => apiFetch<PostureSummary>('/v1/posture/summary'),
	});
}

export function useSuppressHostAdvisory(): UseMutationResult<
	void,
	Error,
	{ id: string; hostId: string; reason: string; expiresAt: string | null }
> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id, reason, expiresAt }) => {
			await apiFetch(`/v1/host-advisories/${encodeURIComponent(id)}/suppress`, {
				method: 'POST',
				body: JSON.stringify({ reason, expires_at: expiresAt }),
			});
		},
		onSuccess: (_, { hostId }) => {
			queryClient.invalidateQueries({ queryKey: ['hosts', hostId, 'advisories'] });
		},
	});
}

export function useUnsuppressHostAdvisory(): UseMutationResult<
	void,
	Error,
	{ id: string; hostId: string }
> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ id }) => {
			await apiFetch(`/v1/host-advisories/${encodeURIComponent(id)}/unsuppress`, {
				method: 'POST',
			});
		},
		onSuccess: (_, { hostId }) => {
			queryClient.invalidateQueries({ queryKey: ['hosts', hostId, 'advisories'] });
		},
	});
}
