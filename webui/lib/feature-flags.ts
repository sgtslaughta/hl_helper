'use client';

export function getFeatureFlag(flagName: string): boolean {
	if (typeof process === 'undefined') {
		return false;
	}

	switch (flagName) {
		case 'webui.logs.enabled':
			return process.env.NEXT_PUBLIC_WEBUI_LOGS_ENABLED !== 'false';
		default:
			return false;
	}
}
