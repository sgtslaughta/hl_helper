'use client';

import { useRouter } from 'next/navigation';
import { useHotkeys } from 'react-hotkeys-hook';

export interface HotkeyBinding {
	keys: string;
	description: string;
	action: () => void;
	category: 'navigation' | 'action' | 'ui';
}

/**
 * Predicate for `useHotkeys({ ignoreEventWhen })` — suppresses global shortcuts
 * when the user is typing into a form input, a contenteditable element, or
 * within a modal dialog (role="dialog"). Without this, keys like `?` or `/`
 * fire global handlers even when typing into a shell-exec command textarea
 * inside the action-confirm dialog.
 */
export function ignoreEventInInputs(e: KeyboardEvent): boolean {
	const t = e.target as Element | null;
	if (!t) return false;
	const tag = t.tagName?.toLowerCase();
	if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
	if (t instanceof HTMLElement && t.isContentEditable) return true;
	// Suppress while a modal dialog is on screen — even if a non-form
	// element inside the dialog has focus.
	if (typeof document !== 'undefined' && document.querySelector('[role="dialog"][aria-modal="true"]')) {
		return true;
	}
	return false;
}

/**
 * Same suppression rule as `ignoreEventInInputs` but for raw
 * `window.addEventListener('keydown', …)` handlers (which don't go through
 * react-hotkeys-hook). Used by panes that bind `j`/`k`/`/` for navigation —
 * these must not fire while typing in an input or inside a modal dialog.
 */
export function isInputContext(e: KeyboardEvent): boolean {
	return ignoreEventInInputs(e);
}

export function useNavigationHotkeys(): void {
	const router = useRouter();

	const opts = { preventDefault: true, ignoreEventWhen: ignoreEventInInputs };
	useHotkeys('g h', () => router.push('/hosts'), opts);
	useHotkeys('g t', () => router.push('/tasks'), opts);
	useHotkeys('g u', () => router.push('/updates'), opts);
	useHotkeys('g c', () => router.push('/containers'), opts);
}

const DEFAULT_HOTKEYS: HotkeyBinding[] = [
	{
		keys: 'cmd+k,ctrl+k',
		description: 'Open command palette',
		action: () => console.log('palette'),
		category: 'ui',
	},
	{
		keys: '?',
		description: 'Show shortcuts',
		action: () => console.log('shortcuts'),
		category: 'ui',
	},
	{
		keys: 'g h',
		description: 'Go to Hosts',
		action: () => console.log('hosts'),
		category: 'navigation',
	},
	{
		keys: 'g t',
		description: 'Go to Tasks',
		action: () => console.log('tasks'),
		category: 'navigation',
	},
	{
		keys: 'g u',
		description: 'Go to Updates',
		action: () => console.log('updates'),
		category: 'navigation',
	},
	{
		keys: 'g c',
		description: 'Go to Containers',
		action: () => console.log('containers'),
		category: 'navigation',
	},
	{
		keys: 'g a',
		description: 'Go to Audit',
		action: () => console.log('audit'),
		category: 'navigation',
	},
	{
		keys: 'g p',
		description: 'Go to Plugins',
		action: () => console.log('plugins'),
		category: 'navigation',
	},
	{
		keys: 'g s',
		description: 'Go to Security',
		action: () => console.log('security'),
		category: 'navigation',
	},
	{
		keys: 'g d',
		description: 'Go to Docs',
		action: () => console.log('docs'),
		category: 'navigation',
	},
	{
		keys: '/',
		description: 'Focus search',
		action: () => console.log('search'),
		category: 'ui',
	},
	{
		keys: 'n',
		description: 'New (context-aware)',
		action: () => console.log('new'),
		category: 'action',
	},
	{
		keys: 'r',
		description: 'Refresh',
		action: () => console.log('refresh'),
		category: 'action',
	},
	{
		keys: ']',
		description: 'Next row',
		action: () => console.log('next'),
		category: 'action',
	},
	{
		keys: '[',
		description: 'Previous row',
		action: () => console.log('prev'),
		category: 'action',
	},
	{
		keys: 'enter',
		description: 'Open selected',
		action: () => console.log('open'),
		category: 'action',
	},
	{
		keys: 'esc',
		description: 'Close panel/dialog',
		action: () => console.log('close'),
		category: 'ui',
	},
	{
		keys: 'cmd+/,ctrl+/',
		description: 'Toggle theme',
		action: () => console.log('theme'),
		category: 'ui',
	},
	{
		keys: 'cmd+\\,ctrl+\\',
		description: 'Toggle sidebar collapse',
		action: () => console.log('sidebar'),
		category: 'ui',
	},
	{
		keys: '.',
		description: 'Quick-action menu',
		action: () => console.log('actions'),
		category: 'action',
	},
];

export function useRegisteredHotkeys(bindings: HotkeyBinding[] = DEFAULT_HOTKEYS): void {
	for (const { keys, action } of bindings) {
		useHotkeys(keys, action);
	}
}

export function getHotkeys(): HotkeyBinding[] {
	return DEFAULT_HOTKEYS;
}
