'use client';

interface TimelineHistogramProps {
	bins: Array<{ total: number; errors: number }>;
}

export function TimelineHistogram({ bins }: TimelineHistogramProps) {
	if (!bins || bins.length === 0) {
		return (
			<div className="w-full h-12 bg-surface border border-hairline rounded flex items-center justify-center text-xs text-text-dim">
				No data
			</div>
		);
	}

	const maxTotal = Math.max(...bins.map(b => b.total || 1), 1);
	const maxErrors = Math.max(...bins.map(b => b.errors || 0), 1);

	return (
		<div className="w-full h-12 bg-surface border border-hairline rounded flex items-end justify-between gap-0.5 p-1">
			{bins.map(bin => {
				const heightPct = bin.total > 0 ? (bin.total / maxTotal) * 100 : 0;
				const errorPct = bin.errors > 0 ? (bin.errors / Math.max(bin.total, maxErrors)) * 100 : 0;
				const binKey = `${bin.total}-${bin.errors}-${heightPct}`;

				return (
					<div
						key={binKey}
						className="flex-1 bg-accent bg-opacity-20 rounded-sm relative"
						style={{ height: `${Math.max(heightPct, 5)}%` }}
						title={`${bin.total} total, ${bin.errors} errors`}
					>
						{errorPct > 0 && (
							<div
								className="absolute bottom-0 left-0 right-0 bg-danger"
								style={{ height: `${errorPct}%` }}
							/>
						)}
					</div>
				);
			})}
		</div>
	);
}
