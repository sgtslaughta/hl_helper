'use client';

import { getFeatureFlag } from '@/lib/feature-flags';
import { ignoreEventInInputs } from '@/lib/hotkeys';
import { useSidebarStore } from '@/stores/sidebar';
import * as Tooltip from '@radix-ui/react-tooltip';
import {
	AlertTriangle,
	Bell,
	BookOpen,
	Boxes,
	Calendar,
	Download,
	Inbox,
	KeyRound,
	ListChecks,
	Lock,
	LogOut,
	Network,
	PanelLeftClose,
	PanelLeftOpen,
	Plug,
	Puzzle,
	ScrollText,
	Server,
	Settings,
	ShieldCheck,
	UserCog,
	Users,
	Webhook,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useHotkeys } from 'react-hotkeys-hook';

interface NavItem {
	icon: LucideIcon;
	label: string;
	href: string;
	hotkey?: string;
	flag?: string;
}

interface NavSection {
	title: string;
	items: NavItem[];
}

const SECTIONS: NavSection[] = [
	{
		title: 'Fleet',
		items: [
			{ icon: Server, label: 'Hosts', href: '/hosts', hotkey: 'g h' },
			{ icon: Boxes, label: 'Containers', href: '/containers', hotkey: 'g c' },
			{ icon: Network, label: 'Topology', href: '/topology', hotkey: 'g x' },
		],
	},
	{
		title: 'Ops',
		items: [
			{ icon: ListChecks, label: 'Tasks', href: '/tasks', hotkey: 'g t' },
			{ icon: Download, label: 'Updates', href: '/updates', hotkey: 'g u' },
			{ icon: Inbox, label: 'Approvals', href: '/approvals' },
			{ icon: Calendar, label: 'Schedules', href: '/schedules' },
			{ icon: ScrollText, label: 'Logs', href: '/logs', flag: 'webui.logs.enabled' },
		],
	},
	{
		title: 'Trust',
		items: [
			{ icon: ShieldCheck, label: 'Security', href: '/security', hotkey: 'g s' },
			{ icon: ScrollText, label: 'Audit', href: '/audit', hotkey: 'g a' },
			{ icon: LogOut, label: 'Sessions', href: '/sessions' },
			{ icon: Users, label: 'Users', href: '/users' },
			{ icon: UserCog, label: 'Roles', href: '/roles' },
			{ icon: KeyRound, label: 'Bindings', href: '/bindings' },
			{ icon: AlertTriangle, label: 'Advisories', href: '/advisories' },
		],
	},
	{
		title: 'Config',
		items: [
			{ icon: Puzzle, label: 'Plugins', href: '/plugins', hotkey: 'g p' },
			{ icon: Plug, label: 'Integrations', href: '/integrations' },
			{ icon: Bell, label: 'Notifications', href: '/notifications' },
			{ icon: Webhook, label: 'Webhooks', href: '/webhooks' },
			{ icon: Lock, label: 'Secrets', href: '/secrets' },
			{ icon: Settings, label: 'Settings', href: '/settings' },
		],
	},
	{
		title: 'Help',
		items: [{ icon: BookOpen, label: 'Docs', href: '/docs', hotkey: 'g d' }],
	},
];

function readInitialCollapsed(): boolean {
	if (typeof document === 'undefined') return false;
	return document.documentElement.dataset.sidebarCollapsed === '1';
}

export function Sidebar() {
	const collapsed = useSidebarStore(state => state.collapsed);
	const hasHydrated = useSidebarStore(state => state.hasHydrated);
	const toggle = useSidebarStore(state => state.toggle);

	useHotkeys('cmd+\\,ctrl+\\', toggle, {
		preventDefault: true,
		ignoreEventWhen: ignoreEventInInputs,
	});

	// Defer inner-content render to client to avoid flash: SSR doesn't know
	// localStorage, so server-rendered icons/text would mismatch the boot
	// script's CSS-var width and flash on hydration.
	const [mounted, setMounted] = useState(false);
	useEffect(() => {
		setMounted(true);
	}, []);

	const effectiveCollapsed = hasHydrated ? collapsed : readInitialCollapsed();
	const ToggleIcon = effectiveCollapsed ? PanelLeftOpen : PanelLeftClose;

	const [animateReady, setAnimateReady] = useState(false);
	useEffect(() => {
		if (!hasHydrated) return;
		const id = requestAnimationFrame(() => setAnimateReady(true));
		return () => cancelAnimationFrame(id);
	}, [hasHydrated]);

	// Sync CSS var with React state after user toggles (post-hydration)
	useEffect(() => {
		if (!hasHydrated || typeof document === 'undefined') return;
		document.documentElement.style.setProperty(
			'--sidebar-w',
			effectiveCollapsed ? '3.5rem' : '15rem',
		);
		document.documentElement.dataset.sidebarCollapsed = effectiveCollapsed ? '1' : '0';
	}, [effectiveCollapsed, hasHydrated]);

	const transitionClass = animateReady ? 'transition-[width] duration-300' : '';

	if (!mounted) {
		// Server + first client render: empty shell. Width comes from CSS var
		// set by /sidebar-init.js (synchronous, pre-paint).
		return (
			<aside
				suppressHydrationWarning
				style={{ width: 'var(--sidebar-w, 15rem)' }}
				className="flex flex-col border-r border-hairline bg-surface"
				aria-label="Primary navigation"
				aria-busy="true"
			/>
		);
	}

	return (
		<Tooltip.Provider delayDuration={200} skipDelayDuration={50}>
			<aside
				suppressHydrationWarning
				style={{ width: 'var(--sidebar-w, 15rem)' }}
				className={`flex flex-col border-r border-hairline bg-surface ${transitionClass}`}
				aria-label="Primary navigation"
			>
				<div
					className={`flex items-center p-3 ${effectiveCollapsed ? 'justify-center' : 'justify-end'}`}
				>
					<Tooltip.Root>
						<Tooltip.Trigger asChild>
							<button
								type="button"
								onClick={toggle}
								aria-label={effectiveCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
								aria-expanded={!effectiveCollapsed}
								className="rounded p-1.5 text-text-dim hover:bg-surface-2 hover:text-text"
							>
								<ToggleIcon size={18} />
							</button>
						</Tooltip.Trigger>
						<Tooltip.Portal>
							<Tooltip.Content
								side="right"
								sideOffset={8}
								className="rounded border border-hairline bg-surface px-2 py-1 text-xs text-text shadow-lg flex items-center gap-2"
							>
								<span>{effectiveCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}</span>
								<kbd className="font-mono text-[10px] text-text-dim">⌘\</kbd>
							</Tooltip.Content>
						</Tooltip.Portal>
					</Tooltip.Root>
				</div>

				<nav className={`flex-1 overflow-auto ${effectiveCollapsed ? 'px-2 py-2' : 'px-4 py-2'}`}>
					{SECTIONS.map(section => (
						<div key={section.title} className="mb-6">
							{!effectiveCollapsed && (
								<h3 className="text-xs font-semibold uppercase tracking-wider text-text-dim mb-3">
									{section.title}
								</h3>
							)}
							<div className="space-y-1">
								{section.items
									.filter(item => !item.flag || getFeatureFlag(item.flag))
									.map(item => {
										const Icon = item.icon;
										const link = (
										<Link
											href={item.href}
											className={`flex items-center rounded text-sm text-text-dim hover:text-text hover:bg-surface-2 transition-colors ${
												effectiveCollapsed
													? 'justify-center px-2 py-2'
													: 'justify-between gap-3 px-3 py-2'
											}`}
											aria-label={effectiveCollapsed ? item.label : undefined}
										>
											{effectiveCollapsed ? (
												<Icon size={18} className="flex-shrink-0" />
											) : (
												<>
													<div className="flex items-center gap-3">
														<Icon size={18} className="flex-shrink-0" />
														<span>{item.label}</span>
													</div>
													{item.hotkey && (
														<kbd className="font-mono text-tiny text-text-dim/70 opacity-0 group-hover:opacity-100 transition-opacity">
															{item.hotkey}
														</kbd>
													)}
												</>
											)}
										</Link>
									);

									return (
										<Tooltip.Root key={item.href}>
											<Tooltip.Trigger asChild>
												<div className="group">{link}</div>
											</Tooltip.Trigger>
											<Tooltip.Portal>
												<Tooltip.Content
													side="right"
													sideOffset={8}
													className="rounded border border-hairline bg-surface px-2 py-1 text-xs text-text shadow-lg flex items-center gap-2"
												>
													<span>{item.label}</span>
													{item.hotkey && (
														<kbd className="font-mono text-[10px] text-text-dim">{item.hotkey}</kbd>
													)}
												</Tooltip.Content>
											</Tooltip.Portal>
										</Tooltip.Root>
									);
								})}
							</div>
						</div>
					))}
				</nav>
			</aside>
		</Tooltip.Provider>
	);
}
