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
			</head>
			<body>
				<ServiceWorkerCleanup />
				{children}
			</body>
		</html>
	);
}
