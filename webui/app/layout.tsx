import type { Metadata } from 'next';
import { ServiceWorkerCleanup } from './sw-unregister';
import './globals.css';

export const metadata: Metadata = {
	title: 'hl_helper',
	description: 'Fleet manager — Security, compliance, automation',
	icons: {
		icon: '/icons/favicon.ico',
		apple: '/icons/apple-touch-icon.png',
	},
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
	return (
		<html lang="en" suppressHydrationWarning>
			<head>
				<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
				<meta name="theme-color" content="#0f1216" />
				<meta name="color-scheme" content="dark light" />
				<link rel="preconnect" href="https://fonts.googleapis.com" />
				<link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
				<link
					rel="stylesheet"
					href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap"
				/>
				{/* Pre-hydration: apply persisted sidebar width before first paint (synchronous) */}
				<script src="/sidebar-init.js" />
			</head>
			<body>
				<ServiceWorkerCleanup />
				{children}
			</body>
		</html>
	);
}
