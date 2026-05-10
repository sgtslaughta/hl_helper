'use client';

export interface BinData {
	total: number;
	errors: number;
}

export function DensitySparkline({ bins }: { bins: BinData[] }) {
	if (!bins || bins.length === 0) {
		return <svg width="100%" height="24" />;
	}

	const maxCount = Math.max(...bins.map(b => b.total), 1);
	const barWidth = 100 / bins.length;
	const svgHeight = 24;
	const padding = 2;

	return (
		<svg width="100%" height={svgHeight} viewBox={`0 0 100 ${svgHeight}`} preserveAspectRatio="none" role="img">
			<title>Activity density sparkline</title>
			{bins.map((bin, i) => {
				const errorRate = bin.total > 0 ? bin.errors / bin.total : 0;
				const isHighError = errorRate > 0.2;

				// Height proportional to total count
				const heightPercent = (bin.total / maxCount) * 100;
				const barHeight = (heightPercent / 100) * (svgHeight - padding);
				const y = svgHeight - barHeight;

				// Color: shift to red when error rate > 20%
				const color = isHighError ? '#ef4444' : '#3b82f6';

				return (
					<rect
						// biome-ignore lint/suspicious/noArrayIndexKey: fixed-order sparkline bins
						key={i}
						x={i * barWidth + padding / 2}
						y={y}
						width={barWidth - padding}
						height={barHeight}
						fill={color}
						opacity={0.8}
					/>
				);
			})}
		</svg>
	);
}
