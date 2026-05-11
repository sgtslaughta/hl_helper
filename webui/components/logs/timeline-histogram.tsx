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

	const maxTotal = Math.max(...bins.map(b => b.total), 1);

	return (
		<div
			className="w-full h-12 bg-surface border border-hairline rounded flex items-end justify-between gap-0.5 px-1 py-1"
			role="img"
			aria-label="Activity histogram (60 bins)"
		>
			{bins.map((bin, i) => {
				const heightPct = bin.total > 0 ? (bin.total / maxTotal) * 100 : 0;
				const errorPct = bin.total > 0 ? (bin.errors / bin.total) * 100 : 0;
				const hasData = bin.total > 0;

				return (
					<div
						// biome-ignore lint/suspicious/noArrayIndexKey: 60 fixed-position bins
						key={`bin-${i}`}
						className={`flex-1 rounded-sm relative ${hasData ? 'bg-accent/60' : 'bg-hairline/40'}`}
						style={{ height: hasData ? `${Math.max(heightPct, 8)}%` : '4%' }}
						title={`${bin.total} events${bin.errors > 0 ? ` · ${bin.errors} errors` : ''}`}
					>
						{errorPct > 0 && (
							<div
								className="absolute bottom-0 left-0 right-0 bg-danger rounded-sm"
								style={{ height: `${errorPct}%` }}
							/>
						)}
					</div>
				);
			})}
		</div>
	);
}
