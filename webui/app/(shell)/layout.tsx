'use client';

import { CommandPalette } from '@/components/shell/command-palette';
import { Providers } from '@/components/shell/providers';
import { Sidebar } from '@/components/shell/sidebar';
import { StatusTicker } from '@/components/shell/ticker';
import { Topbar } from '@/components/shell/topbar';

export default function ShellLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	return (
		<Providers>
			<div className="flex h-screen w-screen flex-col bg-canvas">
				<Topbar />
				<StatusTicker />
				<div className="flex flex-1 overflow-hidden">
					<Sidebar />
					<main className="flex-1 overflow-auto">{children}</main>
				</div>
				<CommandPalette />
			</div>
		</Providers>
	);
}
