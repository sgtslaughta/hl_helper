'use client';

import { ThemeProvider } from 'next-themes';
import { BottomDrawer } from '@/components/shell/bottom-drawer';
import { CommandPalette } from '@/components/shell/command-palette';
import { KeyboardShortcutsOverlay } from '@/components/shell/keyboard-shortcuts-overlay';
import { Providers } from '@/components/shell/providers';
import { Sidebar } from '@/components/shell/sidebar';
import { StatusTicker } from '@/components/shell/ticker';
import { Topbar } from '@/components/shell/topbar';

export function ShellShell({ children }: { children: React.ReactNode }) {
	return (
		<ThemeProvider attribute="data-theme" defaultTheme="dark" enableSystem disableTransitionOnChange>
			<Providers>
				<div className="flex h-screen w-screen flex-col bg-canvas">
					<Topbar />
					<StatusTicker />
					<div className="flex flex-1 overflow-hidden">
						<Sidebar />
						<main className="flex-1 overflow-auto">{children}</main>
					</div>
					<CommandPalette />
					<KeyboardShortcutsOverlay />
					<BottomDrawer />
				</div>
			</Providers>
		</ThemeProvider>
	);
}
