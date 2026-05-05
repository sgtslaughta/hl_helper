'use client';

import { useSearch } from '@/lib/search-client';
import { useRecentsStore } from '@/stores/recents';
import { Command } from 'cmdk';
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
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useHotkeys } from 'react-hotkeys-hook';

const routes = [
	{ label: 'Hosts', href: '/hosts', icon: Server, shortcut: 'g h' },
	{ label: 'Containers', href: '/containers', icon: Boxes, shortcut: 'g c' },
	{ label: 'Topology', href: '/topology', icon: Network, shortcut: 'g x' },
	{ label: 'Tasks', href: '/tasks', icon: ListChecks, shortcut: 'g t' },
	{ label: 'Updates', href: '/updates', icon: Download, shortcut: 'g u' },
	{ label: 'Approvals', href: '/approvals', icon: Inbox, shortcut: '' },
	{ label: 'Schedules', href: '/schedules', icon: Calendar, shortcut: '' },
	{ label: 'Security', href: '/security', icon: ShieldCheck, shortcut: 'g s' },
	{ label: 'Audit', href: '/audit', icon: ScrollText, shortcut: 'g a' },
	{ label: 'Sessions', href: '/sessions', icon: LogOut, shortcut: '' },
	{ label: 'Users', href: '/users', icon: Users, shortcut: '' },
	{ label: 'Roles', href: '/roles', icon: UserCog, shortcut: '' },
	{ label: 'Bindings', href: '/bindings', icon: KeyRound, shortcut: '' },
	{ label: 'Advisories', href: '/advisories', icon: AlertTriangle, shortcut: '' },
	{ label: 'Plugins', href: '/plugins', icon: Puzzle, shortcut: 'g p' },
	{ label: 'Integrations', href: '/integrations', icon: Plug, shortcut: '' },
	{ label: 'Notifications', href: '/notifications', icon: Bell, shortcut: '' },
	{ label: 'Webhooks', href: '/webhooks', icon: Webhook, shortcut: '' },
	{ label: 'Secrets', href: '/secrets', icon: Lock, shortcut: '' },
	{ label: 'Settings', href: '/settings', icon: Settings, shortcut: '' },
	{ label: 'Docs', href: '/docs', icon: BookOpen, shortcut: 'g d' },
];

export function CommandPalette() {
	const [open, setOpen] = useState(false);
	const [searchValue, setSearchValue] = useState('');
	const router = useRouter();
	const recents = useRecentsStore();
	const { data: searchResults = [], isLoading: _searchLoading } = useSearch(searchValue, [
		'hosts',
		'tasks',
		'audit',
	]);

	useHotkeys('cmd+k,ctrl+k', (e: KeyboardEvent) => {
		e.preventDefault();
		setOpen(prev => !prev);
	});

	useEffect(() => {
		const handleEscape = (e: KeyboardEvent) => {
			if (e.key === 'Escape') {
				setOpen(false);
			}
		};

		if (open) {
			document.addEventListener('keydown', handleEscape);
			return () => document.removeEventListener('keydown', handleEscape);
		}
		return;
	}, [open]);

	if (!open) return null;

	const handleNavigate = (href: string) => {
		recents.add({ id: href, label: href, index: 'navigate' });
		router.push(href);
		setOpen(false);
		setSearchValue('');
	};

	const handleSearchResult = (result: { index: string; hit: Record<string, unknown> }) => {
		const id = (result.hit.id as string | undefined) ?? '';
		const label = (result.hit.title as string | undefined) ?? (result.hit.label as string | undefined) ?? '';
		recents.add({ id, label, index: result.index });

		// Navigate to detail page based on index type
		const detailHref = `/${result.index}/${id}`;
		router.push(detailHref);
		setOpen(false);
		setSearchValue('');
	};

	// Filter routes based on search
	const filteredRoutes = searchValue.trim()
		? routes.filter(r => r.label.toLowerCase().includes(searchValue.toLowerCase()))
		: routes;

	// Group search results by index
	const groupedResults = searchResults.reduce(
		(acc, result) => {
			if (!acc[result.index]) {
				acc[result.index] = [];
			}
			acc[result.index].push(result);
			return acc;
		},
		{} as Record<string, typeof searchResults>,
	);

	return (
		<Command.Dialog open={open} onOpenChange={setOpen}>
			<div className="overflow-hidden rounded-lg border border-hairline bg-surface shadow-xl">
				<Command.Input
					placeholder="Search routes or docs..."
					className="w-full border-b border-hairline bg-surface px-4 py-3 text-text outline-none placeholder:text-text-dim"
					value={searchValue}
					onValueChange={setSearchValue}
				/>
				<div className="max-h-96 overflow-auto">
					<Command.List>
						{/* Navigate Section */}
						{!searchValue && (
							<Command.Group heading="Navigate" className="overflow-hidden px-2 py-1.5">
								{routes.map(route => {
									const Icon = route.icon;
									return (
										<Command.Item
											key={route.href}
											value={route.href}
											onSelect={() => handleNavigate(route.href)}
											className="flex cursor-pointer items-center justify-between rounded px-2 py-2 text-sm text-text-dim hover:text-text hover:bg-surface-2 aria-selected:bg-surface-2 aria-selected:text-text"
										>
											<div className="flex items-center gap-2">
												<Icon size={16} />
												<span>{route.label}</span>
											</div>
											{route.shortcut && (
												<span className="text-tiny font-mono text-text-dim opacity-60">
													{route.shortcut}
												</span>
											)}
										</Command.Item>
									);
								})}
							</Command.Group>
						)}

						{/* Filtered Routes */}
						{searchValue && filteredRoutes.length > 0 && (
							<Command.Group heading="Routes" className="overflow-hidden px-2 py-1.5">
								{filteredRoutes.map(route => {
									const Icon = route.icon;
									return (
										<Command.Item
											key={route.href}
											value={route.href}
											onSelect={() => handleNavigate(route.href)}
											className="flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-sm text-text-dim hover:text-text hover:bg-surface-2 aria-selected:bg-surface-2 aria-selected:text-text"
										>
											<Icon size={16} />
											<span>{route.label}</span>
										</Command.Item>
									);
								})}
							</Command.Group>
						)}

						{/* Search Results */}
						{searchValue &&
							Object.keys(groupedResults).length > 0 &&
							Object.entries(groupedResults).map(([index, results]) => (
								<Command.Group
									key={index}
									heading={index.charAt(0).toUpperCase() + index.slice(1)}
									className="overflow-hidden px-2 py-1.5"
								>
									{results.map((result) => (
										<Command.Item
											key={`${index}-${(result.hit.id as string | undefined) ?? (result.hit.title as string | undefined) ?? ''}`}
											value={(result.hit.id as string | undefined) ?? (result.hit.title as string | undefined) ?? ''}
											onSelect={() => handleSearchResult(result)}
											className="flex cursor-pointer flex-col rounded px-2 py-2 hover:bg-surface-2 aria-selected:bg-surface-2"
										>
											<span className="text-sm text-text">
												{((result.hit.title as React.ReactNode) ?? (result.hit.label as React.ReactNode) ?? (result.hit.id as React.ReactNode))}
											</span>
											{result.highlights && (
												<span className="text-tiny text-text-dim opacity-70">
													{(Object.values(result.highlights)[0] as React.ReactNode) ?? ''}
												</span>
											)}
										</Command.Item>
									))}
								</Command.Group>
							))}

						{/* Recent Items */}
						{!searchValue && recents.items.length > 0 && (
							<Command.Group heading="Recent" className="overflow-hidden px-2 py-1.5">
								{recents.items.map(item => (
									<Command.Item
										key={`${item.index}-${item.id}`}
										value={item.id}
										onSelect={() => {
											const href =
												item.index === 'navigate' ? item.id : `/${item.index}/${item.id}`;
											router.push(href);
											setOpen(false);
										}}
										className="flex cursor-pointer items-center gap-2 rounded px-2 py-2 text-sm text-text-dim hover:text-text hover:bg-surface-2 aria-selected:bg-surface-2 aria-selected:text-text"
									>
										<span>{item.label}</span>
										<span className="text-tiny opacity-50">({item.index})</span>
									</Command.Item>
								))}
							</Command.Group>
						)}

						{/* Empty state */}
						{searchValue &&
							filteredRoutes.length === 0 &&
							Object.keys(groupedResults).length === 0 && (
								<Command.Empty className="py-6 text-center text-sm text-text-dim">
									No results found
								</Command.Empty>
							)}
					</Command.List>
				</div>
			</div>
		</Command.Dialog>
	);
}
