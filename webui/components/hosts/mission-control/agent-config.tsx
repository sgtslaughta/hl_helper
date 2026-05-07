'use client';

import { updateHeartbeatInterval, type Host } from '@/lib/api/hosts';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings } from 'lucide-react';
import { useState } from 'react';

export function AgentConfig({ host }: { host: Host }) {
	const qc = useQueryClient();
	const [interval, setInterval] = useState(host.heartbeat_interval_s ?? 60);
	const [saved, setSaved] = useState(false);

	const mut = useMutation({
		mutationFn: (intervalS: number) => updateHeartbeatInterval(host.id, intervalS),
		onSuccess: () => {
			setSaved(true);
			qc.invalidateQueries({ queryKey: ['hosts', host.id] });
			setTimeout(() => setSaved(false), 2000);
		},
	});

	const handleSave = () => {
		if (interval >= 5 && interval <= 3600) {
			mut.mutate(interval);
		}
	};

	return (
		<div className="flex flex-col">
			<div className="mb-1.5 flex items-center gap-1.5">
				<Settings className="text-accent" size={11} />
				<span className="mc-heading">Agent</span>
			</div>
			<div className="mc-bezel space-y-2 px-2.5 py-2 font-mono text-[11px]">
				<label className="block">
					<div className="uppercase tracking-[0.14em] text-text-dim">
						Heartbeat interval (sec)
					</div>
					<div className="mt-1 flex gap-1.5">
						<input
							type="number"
							min={5}
							max={3600}
							value={interval}
							onChange={e => setInterval(Number(e.target.value))}
							className="w-24 rounded-sm border border-hairline bg-bezel/60 px-2 py-1 text-right text-[12px] text-text outline-none focus:border-accent"
							aria-label="Heartbeat interval"
						/>
						<button
							type="button"
							onClick={handleSave}
							disabled={mut.isPending || interval < 5 || interval > 3600}
							className="rounded-sm border border-hairline bg-accent/10 px-2 py-1 text-accent hover:bg-accent/20 disabled:opacity-50"
						>
							{mut.isPending ? '...' : 'Save'}
						</button>
						{saved && (
							<span className="ml-auto flex items-center text-ok">
								Saved
							</span>
						)}
					</div>
				</label>
				<div className="border-t border-hairline pt-2 text-[9px] text-text-dim">
					Range: 5–3600 seconds
				</div>
			</div>
		</div>
	);
}
