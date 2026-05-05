'use client';

import { useSidebarStore } from '@/stores/sidebar';
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
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { useHotkeys } from 'react-hotkeys-hook';

export function Sidebar() {
	const collapsed = useSidebarStore(state => state.collapsed);
	const toggle = useSidebarStore(state => state.toggle);
	const t = useTranslations('nav');

	useHotkeys('cmd+\\,ctrl+\\', toggle, { preventDefault: true });

	const sections = [
		{
			title: t('fleet'),
			items: [
				{ icon: Server, label: 'Hosts', href: '/hosts', key: 'gh' },
				{ icon: Boxes, label: 'Containers', href: '/containers', key: 'gc' },
				{ icon: Network, label: 'Topology', href: '/topology', key: 'gx' },
			],
		},
		{
			title: t('ops'),
			items: [
				{ icon: ListChecks, label: t('tasks'), href: '/tasks', key: 'gt' },
				{ icon: Download, label: t('updates'), href: '/updates', key: 'gu' },
				{ icon: Inbox, label: t('approvals'), href: '/approvals' },
				{ icon: Calendar, label: t('schedules'), href: '/schedules' },
			],
		},
		{
			title: t('trust'),
			items: [
				{ icon: ShieldCheck, label: t('security'), href: '/security', key: 'gs' },
				{ icon: ScrollText, label: t('audit'), href: '/audit', key: 'ga' },
				{ icon: LogOut, label: t('sessions'), href: '/sessions' },
				{ icon: Users, label: t('users'), href: '/users' },
				{ icon: UserCog, label: t('roles'), href: '/roles' },
				{ icon: KeyRound, label: t('bindings'), href: '/bindings' },
				{ icon: AlertTriangle, label: t('advisories'), href: '/advisories' },
			],
		},
		{
			title: t('config'),
			items: [
				{ icon: Puzzle, label: t('plugins'), href: '/plugins', key: 'gp' },
				{ icon: Plug, label: t('integrations'), href: '/integrations' },
				{ icon: Bell, label: t('notifications'), href: '/notifications' },
				{ icon: Webhook, label: t('webhooks'), href: '/webhooks' },
				{ icon: Lock, label: t('secrets'), href: '/secrets' },
				{ icon: Settings, label: t('settings'), href: '/settings' },
			],
		},
		{
			title: t('help'),
			items: [{ icon: BookOpen, label: t('docs'), href: '/docs', key: 'gd' }],
		},
	];

	return (
		<aside
			className={`flex flex-col border-r border-hairline bg-surface transition-all duration-300 ${
				collapsed ? 'w-14' : 'w-60'
			}`}
		>
			<div className="flex items-center justify-between p-4">
				<button type="button" onClick={toggle} className="rounded hover:bg-surface-2 p-1">
					≡
				</button>
			</div>
			{!collapsed && (
				<nav className="flex-1 overflow-auto px-4 py-2">
					{sections.map(section => (
						<div key={section.title} className="mb-6">
							<h3 className="text-xs font-semibold uppercase tracking-wider text-text-dim mb-3">
								{section.title}
							</h3>
							<div className="space-y-1">
								{section.items.map(item => {
									const Icon = item.icon;
									return (
										<Link
											key={item.href}
											href={item.href}
											className="flex items-center justify-between gap-3 px-3 py-2 rounded text-sm text-text-dim hover:text-text hover:bg-surface-2 transition-colors"
										>
											<div className="flex items-center gap-3">
												<Icon size={18} className="flex-shrink-0" />
												<span>{item.label}</span>
											</div>
											{item.key && (
												<span className="text-tiny font-mono text-text-dim">{item.key}</span>
											)}
										</Link>
									);
								})}
							</div>
						</div>
					))}
				</nav>
			)}
		</aside>
	);
}
