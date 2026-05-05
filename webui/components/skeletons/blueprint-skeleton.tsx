'use client';

export function BlueprintSkeleton({ rows = 5 }: { rows?: number }) {
	return (
		<div className="space-y-3 p-4">
			{Array.from({ length: rows }, (_, i) => `skeleton-${i}`).map(key => (
				<div key={key} className="flex gap-4">
					<div className="h-12 w-12 rounded bg-surface-2" />
					<div className="flex-1">
						<div className="mb-2 h-4 w-3/4 rounded bg-surface-2" />
						<div className="h-3 w-1/2 rounded bg-surface" />
					</div>
				</div>
			))}
		</div>
	);
}
