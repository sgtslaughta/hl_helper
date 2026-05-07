import { apiFetch } from '@/lib/api-client';

export interface PendingToken {
	id: string;
	label: string | null;
	prefix: string;
	last_4: string;
	expires_at: string;
	created_at: string;
	created_by: string;
}

export interface MintResponse {
	token_id: string;
	plaintext_token: string;
	expires_at: string;
	install_command: string;
}

export interface MintRequest {
	label: string;
	ttl_seconds: number;
	origin?: string;
}

export interface AdvertisedOrigins {
	origins: string[];
	default: string;
}

export function mintEnrollmentToken(body: MintRequest): Promise<MintResponse> {
	return apiFetch<MintResponse>('/v1/enrollment-tokens', {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

export function getAdvertisedOrigins(): Promise<AdvertisedOrigins> {
	return apiFetch<AdvertisedOrigins>('/v1/system/advertised-origins');
}

export function listPendingTokens(): Promise<PendingToken[]> {
	return apiFetch<PendingToken[]>('/v1/enrollment-tokens');
}

export function revokePendingToken(tokenId: string): Promise<void> {
	return apiFetch<void>(`/v1/enrollment-tokens/${encodeURIComponent(tokenId)}`, {
		method: 'DELETE',
	});
}
