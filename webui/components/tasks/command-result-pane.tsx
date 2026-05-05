'use client';

interface CommandResult {
	exitCode: number;
	stdout: string;
	stderr: string;
}

interface CommandResultPaneProps {
	result: CommandResult;
	isLoading?: boolean;
}

export function CommandResultPane({ result, isLoading = false }: CommandResultPaneProps) {
	return (
		<div className="space-y-4 p-4">
			{isLoading ? (
				<p className="text-text-dim">Waiting for results...</p>
			) : (
				<>
					<div>
						<h3 className="text-sm font-semibold text-text mb-2">Exit Code</h3>
						<div
							className={`inline-block px-3 py-1 rounded text-sm font-mono ${result.exitCode === 0 ? 'bg-ok text-canvas' : 'bg-danger text-canvas'}`}
						>
							{result.exitCode}
						</div>
					</div>

					{result.stdout && (
						<div>
							<h3 className="text-sm font-semibold text-text mb-2">Output</h3>
							<pre className="bg-surface-2 text-text text-xs p-3 rounded overflow-x-auto max-h-48 overflow-y-auto font-mono">
								{result.stdout}
							</pre>
						</div>
					)}

					{result.stderr && (
						<div>
							<h3 className="text-sm font-semibold text-text mb-2">Errors</h3>
							<pre className="bg-danger text-canvas text-xs p-3 rounded overflow-x-auto max-h-48 overflow-y-auto font-mono">
								{result.stderr}
							</pre>
						</div>
					)}
				</>
			)}
		</div>
	);
}
