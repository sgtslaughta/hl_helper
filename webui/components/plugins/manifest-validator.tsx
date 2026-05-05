'use client';

import { Textarea } from '@/components/primitives/textarea';
import { useState } from 'react';

interface ManifestValidatorProps {
	onValid?: (manifest: PluginManifest) => void;
	onInvalid?: (error: string) => void;
}

interface PluginManifest {
	id: string;
	version: string;
	name: string;
	runtime: 'binary' | 'python' | 'node' | 'jvm' | 'wasm';
	capabilities?: string[];
	min_hl_helper_version: string;
	resources: {
		cpu_milli: number;
		memory_mib: number;
		disk_mib: number;
	};
	description?: string;
}

const ALLOWED_CAPABILITIES = new Set([
	'egress.http',
	'egress.tcp',
	'secrets.read',
	'hooks.update.pre',
	'hooks.update.post',
	'hooks.task.created',
	'hooks.notification.route',
	'storage.local',
]);

const RUNTIME_VALUES = ['binary', 'python', 'node', 'jvm', 'wasm'];

function validateId(id: string): string | null {
	const pattern = /^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$/;
	if (!pattern.test(id)) {
		return 'ID must be reverse-DNS format (e.g., com.example.plugin)';
	}
	return null;
}

function validateVersion(version: string): string | null {
	const pattern = /^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$/;
	if (!pattern.test(version)) {
		return 'Version must be semantic (e.g., 1.0.0)';
	}
	return null;
}

function validateManifest(data: unknown): {
	valid: boolean;
	error?: string;
	manifest?: PluginManifest;
} {
	if (!data || typeof data !== 'object' || Array.isArray(data)) {
		return { valid: false, error: 'Manifest must be a JSON object' };
	}

	const manifest = data as Record<string, unknown>;

	// Validate required fields
	if (!manifest.id || typeof manifest.id !== 'string') {
		return { valid: false, error: 'Missing or invalid field: id (string)' };
	}

	if (!manifest.version || typeof manifest.version !== 'string') {
		return { valid: false, error: 'Missing or invalid field: version (string)' };
	}

	if (!manifest.name || typeof manifest.name !== 'string') {
		return { valid: false, error: 'Missing or invalid field: name (string)' };
	}

	if (!manifest.runtime || typeof manifest.runtime !== 'string') {
		return { valid: false, error: 'Missing or invalid field: runtime (string)' };
	}

	if (!manifest.min_hl_helper_version || typeof manifest.min_hl_helper_version !== 'string') {
		return { valid: false, error: 'Missing or invalid field: min_hl_helper_version (string)' };
	}

	if (
		!manifest.resources ||
		typeof manifest.resources !== 'object' ||
		Array.isArray(manifest.resources)
	) {
		return { valid: false, error: 'Missing or invalid field: resources (object)' };
	}

	const resources = manifest.resources as Record<string, unknown>;
	if (
		typeof resources.cpu_milli !== 'number' ||
		resources.cpu_milli < 1 ||
		resources.cpu_milli > 8000
	) {
		return { valid: false, error: 'Invalid: resources.cpu_milli must be 1-8000' };
	}

	if (
		typeof resources.memory_mib !== 'number' ||
		resources.memory_mib < 1 ||
		resources.memory_mib > 8192
	) {
		return { valid: false, error: 'Invalid: resources.memory_mib must be 1-8192' };
	}

	if (
		typeof resources.disk_mib !== 'number' ||
		resources.disk_mib < 0 ||
		resources.disk_mib > 10240
	) {
		return { valid: false, error: 'Invalid: resources.disk_mib must be 0-10240' };
	}

	// Validate ID
	const idError = validateId(manifest.id);
	if (idError) {
		return { valid: false, error: idError };
	}

	// Validate version
	const versionError = validateVersion(manifest.version);
	if (versionError) {
		return { valid: false, error: versionError };
	}

	// Validate min_hl_helper_version
	const minVersionError = validateVersion(manifest.min_hl_helper_version);
	if (minVersionError) {
		return { valid: false, error: `Invalid min_hl_helper_version: ${minVersionError}` };
	}

	// Validate runtime
	if (!RUNTIME_VALUES.includes(manifest.runtime as string)) {
		return { valid: false, error: `Invalid runtime: must be one of ${RUNTIME_VALUES.join(', ')}` };
	}

	// Validate capabilities
	const capabilities = (manifest.capabilities || []) as unknown[];
	if (!Array.isArray(capabilities)) {
		return { valid: false, error: 'Invalid: capabilities must be an array' };
	}

	for (const cap of capabilities) {
		if (typeof cap !== 'string') {
			return { valid: false, error: 'Invalid: each capability must be a string' };
		}
		if (!ALLOWED_CAPABILITIES.has(cap)) {
			return { valid: false, error: `Invalid capability: ${cap}` };
		}
	}

	return {
		valid: true,
		manifest: {
			id: manifest.id as string,
			version: manifest.version as string,
			name: manifest.name as string,
			runtime: manifest.runtime as 'binary' | 'python' | 'node' | 'jvm' | 'wasm',
			capabilities: capabilities as string[],
			min_hl_helper_version: manifest.min_hl_helper_version as string,
			resources: {
				cpu_milli: resources.cpu_milli as number,
				memory_mib: resources.memory_mib as number,
				disk_mib: resources.disk_mib as number,
			},
			description: typeof manifest.description === 'string' ? manifest.description : undefined,
		},
	};
}

export function ManifestValidator({ onValid, onInvalid }: ManifestValidatorProps) {
	const [input, setInput] = useState('');
	const [error, setError] = useState<string | null>(null);

	const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
		const value = e.target.value;
		setInput(value);

		if (!value.trim()) {
			setError(null);
			return;
		}

		try {
			const data = JSON.parse(value);
			const result = validateManifest(data);

			if (result.valid && result.manifest) {
				setError(null);
				onValid?.(result.manifest);
			} else {
				setError(result.error || 'Validation failed');
				onInvalid?.(result.error || 'Validation failed');
			}
		} catch (e) {
			const errorMsg = `Invalid JSON: ${e instanceof Error ? e.message : String(e)}`;
			setError(errorMsg);
			onInvalid?.(errorMsg);
		}
	};

	return (
		<Textarea
			label="Plugin Manifest"
			hint="JSON format - TODO: switch to YAML when js-yaml added"
			placeholder='{"id": "com.example.plugin", "version": "1.0.0", ...}'
			value={input}
			onChange={handleChange}
			error={error || undefined}
			rows={12}
		/>
	);
}
