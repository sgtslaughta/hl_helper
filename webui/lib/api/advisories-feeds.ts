import { apiFetch } from '@/lib/api-client';
import {
	useMutation,
	useQuery,
	useQueryClient,
	type UseMutationResult,
	type UseQueryResult,
} from '@tanstack/react-query';

export interface FeedStatus {
	feed: string;
	last_sync_at: string | null;
	last_count: number;
	last_error: string | null;
	next_scheduled_at: string | null;
	in_progress: boolean;
}

export interface FeedStatusResponse {
	feeds: FeedStatus[];
}

export interface FeedSyncResponse {
	status: 'accepted' | 'queue_full' | 'disabled';
	feeds: string[];
}

const STATUS_KEY = ['advisory-feeds', 'status'] as const;

export function useFeedStatus(): UseQueryResult<FeedStatusResponse> {
	return useQuery<FeedStatusResponse>({
		queryKey: STATUS_KEY,
		queryFn: () => apiFetch<FeedStatusResponse>('/v1/advisories/feeds/status'),
		refetchInterval: 30_000,
	});
}

export function useTriggerFeedSync(): UseMutationResult<
	FeedSyncResponse,
	Error,
	'osv' | 'epss' | 'kev' | 'all'
> {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (feed) =>
			apiFetch<FeedSyncResponse>(
				`/v1/advisories/feeds/sync?feed=${encodeURIComponent(feed)}`,
				{ method: 'POST' },
			),
		onSuccess: () => {
			qc.invalidateQueries({ queryKey: STATUS_KEY });
		},
	});
}
