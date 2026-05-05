'use client';

import { pauseFocusRefetch } from '@/lib/query-cache';
import { getRuntimeConfig } from '@/lib/runtime-config';
import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon } from '@xterm/addon-search';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useEffect, useRef } from 'react';

interface TerminalPaneProps {
	hostId: string;
	onClose?: () => void;
	onSplit?: () => void;
}

export function TerminalPane({ hostId }: TerminalPaneProps) {
	const containerRef = useRef<HTMLDivElement>(null);
	const terminalRef = useRef<Terminal | null>(null);
	const wsRef = useRef<WebSocket | null>(null);
	const fitAddonRef = useRef<FitAddon | null>(null);
	const resizeObserverRef = useRef<ResizeObserver | null>(null);

	useEffect(() => {
		if (!containerRef.current) return;

		// Initialize terminal
		const terminal = new Terminal({
			theme: {
				background: 'rgb(15 18 22)',
				foreground: 'rgb(230 234 240)',
				cursor: 'rgb(0 224 255)',
				selectionBackground: 'rgb(0 152 173)',
				black: '#1a1d22',
				red: '#ff5c5c',
				green: '#39d98a',
				yellow: '#ffb020',
				blue: '#00e0ff',
				magenta: '#a78bfa',
				cyan: '#00e0ff',
				white: '#e6eaf0',
				brightBlack: '#5c6470',
				brightRed: '#ff7878',
				brightGreen: '#5fe6a3',
				brightYellow: '#ffc04a',
				brightBlue: '#33e8ff',
				brightMagenta: '#b9a4f5',
				brightCyan: '#33e8ff',
				brightWhite: '#ffffff',
			},
			fontFamily: 'var(--font-mono)',
			fontSize: 13,
			lineHeight: 1.2,
		});

		// Attach addons
		const fitAddon = new FitAddon();
		const searchAddon = new SearchAddon();
		const webLinksAddon = new WebLinksAddon();

		terminal.loadAddon(fitAddon);
		terminal.loadAddon(searchAddon);
		terminal.loadAddon(webLinksAddon);

		// Open terminal
		terminal.open(containerRef.current);
		fitAddon.fit();

		terminalRef.current = terminal;
		fitAddonRef.current = fitAddon;

		// Connect to WebSocket
		const setupWebSocket = async () => {
			try {
				const config = await getRuntimeConfig();
				// TODO: backend WS protocol for terminal endpoint
				const wsUrl = `${config.wsBase.replace('http', 'ws')}/api/proxy/v1/agents/${hostId}/terminal`;

				const ws = new WebSocket(wsUrl);

				ws.onopen = () => {
					terminal.write('\x1b[1;32mConnected to terminal\r\n\x1b[0m');
				};

				ws.onmessage = (event: MessageEvent) => {
					terminal.write(event.data);
				};

				ws.onerror = () => {
					terminal.write('\x1b[1;31mWebSocket error\r\n\x1b[0m');
				};

				ws.onclose = () => {
					terminal.write('\x1b[1;31mConnection closed\r\n\x1b[0m');
				};

				// Handle terminal input
				terminal.onData(data => {
					if (ws.readyState === WebSocket.OPEN) {
						ws.send(JSON.stringify({ type: 'input', data }));
					}
				});

				wsRef.current = ws;
			} catch (e) {
				terminal.write(`\x1b[1;31mFailed to connect: ${String(e)}\r\n\x1b[0m`);
			}
		};

		setupWebSocket();

		// Resize observer for container
		const resizeObserver = new ResizeObserver(() => {
			if (fitAddonRef.current && containerRef.current) {
				fitAddonRef.current.fit();
			}
		});

		resizeObserver.observe(containerRef.current);
		resizeObserverRef.current = resizeObserver;

		// Focus/blur handlers for query cache
		const handleFocus = () => pauseFocusRefetch(true);
		const handleBlur = () => pauseFocusRefetch(false);

		containerRef.current.addEventListener('focus', handleFocus);
		containerRef.current.addEventListener('blur', handleBlur);

		return () => {
			pauseFocusRefetch(false);
			if (containerRef.current) {
				containerRef.current.removeEventListener('focus', handleFocus);
				containerRef.current.removeEventListener('blur', handleBlur);
			}
			if (resizeObserverRef.current) {
				resizeObserverRef.current.disconnect();
			}
			if (wsRef.current) {
				wsRef.current.close();
			}
			if (terminalRef.current) {
				terminalRef.current.dispose();
			}
		};
	}, [hostId]);

	return (
		<div
			ref={containerRef}
			className="h-full w-full overflow-hidden rounded bg-canvas"
			style={{ minHeight: '100px' }}
		/>
	);
}
