import type { TickerEvent } from './ticker-types';

// Resolve an internal route for a ticker event. Producers can set `link`
// explicitly; otherwise we derive from `meta` keys.
export function resolveLink(event: TickerEvent): string | null {
	if (event.link) return event.link;
	const meta = event.meta;
	if (!meta) return null;
	const hostId = typeof meta.host_id === 'string' ? meta.host_id : null;
	const advisoryId = typeof meta.advisory_id === 'string' ? meta.advisory_id : null;
	if (advisoryId) return `/advisories?focus=${encodeURIComponent(advisoryId)}`;
	if (hostId) return `/hosts/${encodeURIComponent(hostId)}`;
	return null;
}
