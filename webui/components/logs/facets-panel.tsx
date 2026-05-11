'use client';

import type { FacetBucket } from '@/lib/api/logs';

interface FacetsPanelProps {
	facets?: Record<string, FacetBucket[]>;
}

export function FacetsPanel({ facets }: FacetsPanelProps) {
	if (!facets || Object.keys(facets).length === 0) {
		return (
			<div className="w-48 border-l border-hairline bg-surface-alt p-4 text-xs text-text-dim">
				No facet data
			</div>
		);
	}

	return (
		<div className="w-48 border-l border-hairline bg-surface-alt p-4 flex flex-col gap-4 overflow-y-auto">
			{Object.entries(facets).map(([facetName, buckets]) => (
				<div key={facetName}>
					<h3 className="text-xs font-semibold text-text mb-2 uppercase">{facetName}</h3>
					<ul className="space-y-1">
						{buckets.slice(0, 5).map(bucket => (
							<li
								key={bucket.value}
								className="flex items-center justify-between text-xs text-text-dim hover:text-text cursor-pointer group"
							>
								<span className="truncate group-hover:underline" title={bucket.value}>
									{bucket.value}
								</span>
								<span className="ml-2 shrink-0 font-semibold">{bucket.count}</span>
							</li>
						))}
					</ul>
				</div>
			))}
		</div>
	);
}
