'use client';

import type { QueryClient } from '@tanstack/react-query';
import { getRuntimeConfig } from './runtime-config';

export interface WSMessage {
	channel: string;
	event: string;
	data: Record<string, unknown>;
	seq: number;
}

interface ReconnectConfig {
	initialDelay: number;
	maxDelay: number;
	maxRetries: number;
	jitter: boolean;
}

export class WSClient {
	private ws: WebSocket | null = null;
	private queryClient: QueryClient | null = null;
	private reconnectConfig: ReconnectConfig = {
		initialDelay: 1000,
		maxDelay: 30000,
		maxRetries: Number.POSITIVE_INFINITY,
		jitter: true,
	};
	private reconnectAttempts = 0;
	private lastSeq = 0;
	private subscriptions = new Set<string>();
	private heartbeatInterval: NodeJS.Timeout | null = null;
	private messageQueue: WSMessage[] = [];
	private isReconnecting = false;

	constructor(queryClient: QueryClient) {
		this.queryClient = queryClient;
	}

	async connect(): Promise<void> {
		if (this.ws) return;

		const config = await getRuntimeConfig();
		const wsUrl = config.wsBase;

		return new Promise((resolve, reject) => {
			try {
				this.ws = new WebSocket(wsUrl);

				this.ws.onopen = () => {
					this.reconnectAttempts = 0;
					this.setupHeartbeat();
					this.resumeFromSeq(this.lastSeq);
					this.processQueue();
					resolve();
				};

				this.ws.onmessage = event => {
					try {
						const msg: WSMessage = JSON.parse(event.data);
						this.lastSeq = msg.seq;
						this.onMessage(msg);
					} catch (e) {
						console.error('Failed to parse WS message:', e);
					}
				};

				this.ws.onerror = event => {
					console.error('WS error:', event);
					reject(new Error('WebSocket connection failed'));
				};

				this.ws.onclose = () => {
					this.cleanup();
					if (!this.isReconnecting) {
						this.reconnect();
					}
				};
			} catch (e) {
				reject(e);
			}
		});
	}

	private setupHeartbeat(): void {
		this.heartbeatInterval = setInterval(() => {
			if (this.ws?.readyState === WebSocket.OPEN) {
				this.ws.send(JSON.stringify({ type: 'ping' }));
			}
		}, 30000);
	}

	private cleanup(): void {
		if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
		if (this.ws) this.ws.close();
		this.ws = null;
	}

	private async reconnect(): Promise<void> {
		if (this.isReconnecting) return;
		this.isReconnecting = true;

		const delay = Math.min(
			this.reconnectConfig.initialDelay * 2 ** this.reconnectAttempts,
			this.reconnectConfig.maxDelay,
		);

		const jitteredDelay = this.reconnectConfig.jitter
			? delay + Math.random() * (delay * 0.1)
			: delay;

		await new Promise(r => setTimeout(r, jitteredDelay));
		this.reconnectAttempts++;

		try {
			await this.connect();
		} catch (e) {
			console.error('Reconnect failed:', e);
			if (this.reconnectAttempts < this.reconnectConfig.maxRetries) {
				this.isReconnecting = false;
				await this.reconnect();
			}
		}

		this.isReconnecting = false;
	}

	private resumeFromSeq(seq: number): void {
		if (this.ws?.readyState === WebSocket.OPEN) {
			this.ws.send(JSON.stringify({ type: 'resume', since_seq: seq }));
		}
	}

	private onMessage(msg: WSMessage): void {
		if (!this.queryClient) return;

		// Patch cache based on channel
		const parts = msg.channel.split('.');
		const resource = parts[0];

		if (msg.event === 'update' && msg.data) {
			const queryKey = [resource];
			const current = this.queryClient.getQueryData(queryKey);

			if (Array.isArray(current)) {
				const updated = current.map((item: Record<string, unknown>) => {
					if (item.id === msg.data.id) {
						return { ...item, ...msg.data };
					}
					return item;
				});

				this.queryClient.setQueryData(queryKey, updated);
			} else if (typeof current === 'object' && current !== null) {
				this.queryClient.setQueryData(queryKey, { ...current, ...msg.data });
			}
		} else if (msg.event === 'delete' && msg.data?.id) {
			const queryKey = [resource];
			const current = this.queryClient.getQueryData(queryKey);

			if (Array.isArray(current)) {
				const filtered = current.filter((item: Record<string, unknown>) => item.id !== msg.data.id);
				this.queryClient.setQueryData(queryKey, filtered);
			}
		} else if (msg.event === 'create') {
			const queryKey = [resource];
			const current = this.queryClient.getQueryData(queryKey);

			if (Array.isArray(current)) {
				this.queryClient.setQueryData(queryKey, [msg.data, ...current]);
			}
		}
	}

	subscribe(channel: string): void {
		this.subscriptions.add(channel);
		if (this.ws?.readyState === WebSocket.OPEN) {
			this.messageQueue.push({
				channel: 'control',
				event: 'subscribe',
				data: { channel },
				seq: this.lastSeq,
			});
		}
	}

	unsubscribe(channel: string): void {
		this.subscriptions.delete(channel);
		if (this.ws?.readyState === WebSocket.OPEN) {
			this.messageQueue.push({
				channel: 'control',
				event: 'unsubscribe',
				data: { channel },
				seq: this.lastSeq,
			});
		}
	}

	private processQueue(): void {
		while (this.messageQueue.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
			const msg = this.messageQueue.shift();
			if (msg) {
				this.ws.send(JSON.stringify(msg));
			}
		}
	}

	disconnect(): void {
		this.cleanup();
	}
}

let globalWSClient: WSClient | null = null;

export function getWSClient(queryClient: QueryClient): WSClient {
	if (!globalWSClient) {
		globalWSClient = new WSClient(queryClient);
	}
	return globalWSClient;
}
