'use client';

export const dynamic = 'force-dynamic';

import { EmptyState } from '@/components/empty-states/empty-state';

export default function TopologyPage() {
	return (
		<div className="p-4">
			<div className="mb-6">
				<h1 className="text-h2 font-bold text-text mb-2">Topology</h1>
				<p className="text-text-dim">Visualize infrastructure relationships</p>
			</div>

			<EmptyState
				title="Network Topology"
				description="Wave 3 will load @xyflow/react for interactive visualization"
			/>
		</div>
	);
}
