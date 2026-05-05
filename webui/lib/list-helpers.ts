/**
 * Backend list endpoints have inconsistent shapes during the C-track rollout:
 *   - bare arrays:           []
 *   - paginated:             { items: [...], next_cursor: string|null }
 *   - keyed envelopes:       { users: [...] } / { plugins: [...] } / { webhooks: [...] }
 *
 * `toList` accepts any of those and returns a guaranteed array so render code
 * can call `.map` without runtime "data.map is not a function" crashes. Pages
 * should normalize through this until backend shapes converge on a single
 * pagination contract.
 */
export function toList<T>(
	data: unknown,
	envelopeKey?: string,
): T[] {
	if (Array.isArray(data)) return data as T[];
	if (data && typeof data === 'object') {
		const obj = data as Record<string, unknown>;
		if (Array.isArray(obj.items)) return obj.items as T[];
		if (envelopeKey && Array.isArray(obj[envelopeKey])) return obj[envelopeKey] as T[];
		// Last-resort: if there's exactly one array-valued key, take it.
		const arrays = Object.values(obj).filter(Array.isArray);
		if (arrays.length === 1) return arrays[0] as T[];
	}
	return [];
}
