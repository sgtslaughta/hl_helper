'use client';

import { useEffect } from 'react';

/**
 * Unregisters any previously installed service worker. Older builds shipped
 * Serwist which cached redirected (307) login responses, breaking the auth
 * flow. Mounting this once on shell boot purges those workers.
 */
export function ServiceWorkerCleanup() {
	useEffect(() => {
		if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
		navigator.serviceWorker
			.getRegistrations()
			.then(regs => {
				for (const r of regs) r.unregister();
			})
			.catch(() => {
				// no-op
			});
	}, []);
	return null;
}
