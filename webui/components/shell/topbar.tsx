'use client';

import { apiFetch } from '@/lib/api-client';
import { useAuth } from '@/lib/auth';
import { useSidebarStore } from '@/stores/sidebar';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useQuery } from '@tanstack/react-query';
import { Bell, LogOut, Moon, Settings, Sun, User } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useState } from 'react';

interface UnreadCount {
	count: number;
}

type Density = 'compact' | 'comfortable' | 'spacious';

export function Topbar() {
	const { theme, setTheme, systemTheme } = useTheme();
	const currentTheme = theme === 'system' ? systemTheme : theme;
	const { user, logout } = useAuth();
	const [density, setDensity] = useState<Density>('comfortable');
	const toggle = useSidebarStore(state => state.toggle);

	const { data: unreadCount = { count: 0 } } = useQuery<UnreadCount>({
		queryKey: ['notifications', 'unread-count'],
		queryFn: async () => {
			try {
				return await apiFetch<UnreadCount>('/v1/notifications/unread-count');
			} catch {
				return { count: 0 };
			}
		},
		refetchInterval: 30000,
	});

	const handleThemeToggle = () => {
		const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
		setTheme(nextTheme);
	};

	const handleDensityChange = (newDensity: Density) => {
		setDensity(newDensity);
		if (typeof window !== 'undefined') {
			document.body.setAttribute('data-density', newDensity);
			localStorage.setItem('density', newDensity);
		}
		// Persist to server if authenticated
		if (user?.id) {
			apiFetch('/v1/users/me/prefs', {
				method: 'PATCH',
				body: JSON.stringify({ density: newDensity }),
			}).catch(() => {
				// Fail silently
			});
		}
	};

	const handleLogout = async () => {
		try {
			await logout();
		} catch {
			// Error handling already in logout
		}
	};

	return (
		<header className="flex h-12 items-center justify-between border-b border-hairline bg-surface px-4">
			<div className="flex items-center gap-4">
				<button
					type="button"
					onClick={toggle}
					className="rounded px-2 py-1 hover:bg-surface-2 text-text-dim hover:text-text"
					title="Toggle sidebar"
				>
					⌘\
				</button>
			</div>
			<div className="flex items-center gap-4">
				<a
					href="/notifications"
					className="relative rounded px-2 py-1 hover:bg-surface-2 text-text-dim hover:text-text"
					title="Notifications"
				>
					<Bell size={18} />
					{unreadCount.count > 0 && (
						<span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-danger" />
					)}
				</a>

				<DropdownMenu.Root>
					<DropdownMenu.Trigger asChild>
						<button
							type="button"
							className="flex items-center gap-2 rounded px-2 py-1 hover:bg-surface-2 text-text-dim hover:text-text"
							title="Account menu"
						>
							<User size={18} />
						</button>
					</DropdownMenu.Trigger>
					<DropdownMenu.Content
						className="min-w-48 rounded border border-hairline bg-surface p-1 shadow-lg"
						sideOffset={8}
					>
						<DropdownMenu.Item className="px-3 py-2 text-sm text-text-dim data-[highlighted]:bg-surface-2 data-[highlighted]:text-text cursor-pointer rounded">
							<a href="/settings/profile">Profile</a>
						</DropdownMenu.Item>

						<DropdownMenu.Sub>
							<DropdownMenu.SubTrigger className="flex items-center justify-between px-3 py-2 text-sm text-text-dim data-[highlighted]:bg-surface-2 data-[highlighted]:text-text cursor-pointer rounded">
								Theme
								<span className="text-xs text-text-dim ml-2">→</span>
							</DropdownMenu.SubTrigger>
							<DropdownMenu.SubContent className="min-w-40 rounded border border-hairline bg-surface p-1 shadow-lg">
								<DropdownMenu.Item
									onClick={handleThemeToggle}
									className="flex items-center gap-2 px-3 py-2 text-sm text-text data-[highlighted]:bg-surface-2 cursor-pointer rounded"
								>
									{currentTheme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
									{currentTheme === 'dark' ? 'Light' : 'Dark'}
								</DropdownMenu.Item>
							</DropdownMenu.SubContent>
						</DropdownMenu.Sub>

						<DropdownMenu.Sub>
							<DropdownMenu.SubTrigger className="flex items-center justify-between px-3 py-2 text-sm text-text-dim data-[highlighted]:bg-surface-2 data-[highlighted]:text-text cursor-pointer rounded">
								Density
								<span className="text-xs text-text-dim ml-2">→</span>
							</DropdownMenu.SubTrigger>
							<DropdownMenu.SubContent className="min-w-40 rounded border border-hairline bg-surface p-1 shadow-lg">
								{(['compact', 'comfortable', 'spacious'] as const).map(d => (
									<DropdownMenu.Item
										key={d}
										onClick={() => handleDensityChange(d)}
										className={`px-3 py-2 text-sm cursor-pointer rounded capitalize ${
											density === d
												? 'bg-surface-2 text-text'
												: 'text-text-dim data-[highlighted]:bg-surface-2 data-[highlighted]:text-text'
										}`}
									>
										{d}
									</DropdownMenu.Item>
								))}
							</DropdownMenu.SubContent>
						</DropdownMenu.Sub>

						<DropdownMenu.Item
							onClick={() => {
								window.location.href = '/settings';
							}}
							className="flex items-center gap-2 px-3 py-2 text-sm text-text-dim data-[highlighted]:bg-surface-2 data-[highlighted]:text-text cursor-pointer rounded"
						>
							<Settings size={16} />
							Settings
						</DropdownMenu.Item>

						<DropdownMenu.Separator className="my-1 h-px bg-hairline" />

						<DropdownMenu.Item
							onClick={handleLogout}
							className="flex items-center gap-2 px-3 py-2 text-sm text-danger data-[highlighted]:bg-surface-2 cursor-pointer rounded"
						>
							<LogOut size={16} />
							Sign Out
						</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			</div>
		</header>
	);
}
