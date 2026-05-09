'use client';

import { ServiceWorkerCleanup } from '@/app/sw-unregister';
import { BottomDrawer } from '@/components/shell/bottom-drawer';
import { CommandPalette } from '@/components/shell/command-palette';
import { KeyboardShortcutsOverlay } from '@/components/shell/keyboard-shortcuts-overlay';
import { Providers } from '@/components/shell/providers';
import { Sidebar } from '@/components/shell/sidebar';
import { FooterTicker } from '@/components/shell/ticker/footer-ticker';
import { Topbar } from '@/components/shell/topbar';
import { ThemeProvider } from 'next-themes';

export function ShellShell({ children }: { children: React.ReactNode }) {
	return (
		<ThemeProvider
			attribute="data-theme"
			defaultTheme="dark"
			enableSystem
			disableTransitionOnChange
		>
			<ServiceWorkerCleanup />
			<Providers>
				<div className="flex h-screen w-screen flex-col bg-canvas">
					<Topbar />
					<div className="flex flex-1 overflow-hidden">
						<Sidebar />
						<main className="flex-1 overflow-auto">{children}</main>
					</div>
					<FooterTicker />
					<CommandPalette />
					<KeyboardShortcutsOverlay />
					<BottomDrawer />
				</div>
			</Providers>
		</ThemeProvider>
	);
}
