'use client';

import { apiFetch } from '@/lib/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

export interface RiskDriver {
	label: string;
	contrib: number;
	href?: string | null;
}

export interface PillarOut {
	name: string;
	label: string;
	score: number;
	confidence: number;
	weight: number;
	drivers: RiskDriver[];
	coverage_notes: string[];
	exposure_counts?: Record<string, number>;
}

export interface HostRiskOut {
	host_id: string;
	score: number | null;
	level: 'minimal' | 'stable' | 'moderate' | 'elevated' | 'high' | 'severe' | 'unknown';
	confidence: number;
	pillars: PillarOut[];
	floor_triggered: boolean;
	computed_at: string;
	inputs_hash: string;
}

export interface RiskScorer {
	name: string;
	label: string;
	description: string;
	weight: number;
	weight_default: number;
	enabled: boolean;
	enabled_by_default: boolean;
	plugin: string;
}

export interface RiskConfig {
	weights: Record<string, number>;
	scorers: RiskScorer[];
}

export function useHostRisk(hostId: string) {
	return useQuery<HostRiskOut>({
		queryKey: ['hosts', hostId, 'risk'],
		queryFn: () => apiFetch<HostRiskOut>(`/v1/hosts/${encodeURIComponent(hostId)}/risk`),
		refetchInterval: 30_000,
		enabled: !!hostId,
	});
}

export function useRiskConfig() {
	return useQuery<RiskConfig>({
		queryKey: ['posture-risk-config'],
		queryFn: () => apiFetch<RiskConfig>('/v1/posture/risk/config'),
		staleTime: 60_000,
	});
}

export function useRiskRecompute() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (hostId: string) =>
			apiFetch(`/v1/hosts/${encodeURIComponent(hostId)}/risk/recompute`, { method: 'POST' }),
		onSuccess: (_d, hostId) => {
			qc.invalidateQueries({ queryKey: ['hosts', hostId, 'risk'] });
		},
	});
}

export function usePatchRiskConfig() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (body: {
			weights?: Record<string, number>;
			enabled?: Record<string, boolean>;
		}) =>
			apiFetch<RiskConfig>('/v1/posture/risk/config', {
				method: 'PATCH',
				body: JSON.stringify(body),
			}),
		onSuccess: () => qc.invalidateQueries({ queryKey: ['posture-risk-config'] }),
	});
}
