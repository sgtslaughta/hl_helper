'use client';

import type { Dispatch, SetStateAction } from 'react';

interface Props {
	command: string;
	setCommand: Dispatch<SetStateAction<string>>;
	timeoutS: number;
	setTimeoutS: Dispatch<SetStateAction<number>>;
	asRoot: boolean;
	setAsRoot: Dispatch<SetStateAction<boolean>>;
	reason: string;
	setReason: Dispatch<SetStateAction<string>>;
}

export function ShellExecForm({
	command,
	setCommand,
	timeoutS,
	setTimeoutS,
	asRoot,
	setAsRoot,
	reason,
	setReason,
}: Props) {
	return (
		<div className="mb-3 space-y-2">
			<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
				Command
				<textarea
					value={command}
					onChange={e => setCommand(e.target.value)}
					rows={6}
					spellCheck={false}
					placeholder="$ "
					className="mt-1 w-full resize-y rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] leading-relaxed text-text outline-none focus:border-accent"
				/>
			</label>
			<div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-text-dim">
				<span>Timeout</span>
				<input
					type="number"
					min={1}
					value={timeoutS}
					onChange={e => setTimeoutS(Math.max(1, Number.parseInt(e.target.value) || 1))}
					aria-label="Timeout seconds"
					className="w-20 rounded-sm border border-hairline bg-bezel/60 px-2 py-1 text-right font-mono text-[12px] text-text outline-none focus:border-accent"
				/>
				<span className="text-text-dim normal-case">seconds</span>
			</div>
			<div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-text-dim">
				<input
					type="checkbox"
					id="as-root"
					checked={asRoot}
					onChange={e => setAsRoot(e.target.checked)}
					className="accent-warn"
				/>
				<label htmlFor="as-root" className="cursor-pointer">
					Run elevated (as root)
				</label>
			</div>
			{asRoot ? (
				<>
					<div className="rounded-sm border border-warn/40 bg-warn/10 p-2 font-mono text-[11px] text-warn">
						<span className="font-semibold uppercase tracking-wider">⚠ ELEVATED EXECUTION</span>
						{' '}— runs as <code>root</code> on the target host. Irreversible system changes possible. All actions logged and audited.
					</div>
					<label className="block font-mono text-[11px] uppercase tracking-wider text-text-dim">
						Reason <span className="text-text-dim normal-case">(optional, audited)</span>
						<textarea
							aria-label="Reason"
							value={reason}
							onChange={e => setReason(e.target.value)}
							rows={2}
							placeholder="Why does this need root?"
							className="mt-1 w-full resize-y rounded-sm border border-hairline bg-canvas px-2 py-1.5 font-mono text-[13px] leading-relaxed text-text outline-none focus:border-warn"
						/>
					</label>
				</>
			) : null}
		</div>
	);
}
