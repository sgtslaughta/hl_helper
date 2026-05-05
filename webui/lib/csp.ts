export function generateCSPHeader(nonce: string): string {
	return [
		"default-src 'self'",
		`script-src 'self' 'nonce-${nonce}'`,
		`style-src 'self' 'nonce-${nonce}'`,
		"img-src 'self' data:",
		"font-src 'self'",
		"connect-src 'self'",
		"frame-ancestors 'self'",
		'base-uri "self"',
		"form-action 'self'",
	].join('; ');
}

export function generateNonce(): string {
	if (typeof crypto !== 'undefined') {
		return crypto.getRandomValues(new Uint8Array(16)).reduce((acc, byte) => {
			return acc + byte.toString(16).padStart(2, '0');
		}, '');
	}
	return Math.random().toString(36).substring(2, 15);
}
