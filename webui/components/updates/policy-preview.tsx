'use client';

interface Policy {
	name: string;
	description?: string;
	rules?: Array<{
		name: string;
		action: string;
	}>;
}

interface PolicyPreviewProps {
	policy: Policy;
}

export function PolicyPreview({ policy }: PolicyPreviewProps) {
	return (
		<div className="rounded border border-hairline bg-surface p-4">
			<h3 className="text-sm font-semibold text-text mb-2">{policy.name}</h3>
			{policy.description && <p className="text-xs text-text-dim mb-4">{policy.description}</p>}

			{policy.rules && policy.rules.length > 0 && (
				<div className="space-y-2">
					<h4 className="text-xs font-medium text-text-dim uppercase">Rules</h4>
					{policy.rules.map(rule => (
						<div key={rule.name} className="text-xs bg-surface-2 p-2 rounded">
							<span className="text-text font-mono">{rule.name}</span>
							<span className="text-text-dim mx-2">→</span>
							<span className="text-accent">{rule.action}</span>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
