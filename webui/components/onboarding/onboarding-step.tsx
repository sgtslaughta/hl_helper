'use client';

interface OnboardingStepProps {
	step: number;
	totalSteps?: number;
	headline: string;
	children?: React.ReactNode;
	footer?: React.ReactNode;
}

export function OnboardingStep({
	step,
	totalSteps = 5,
	headline,
	children,
	footer,
}: OnboardingStepProps) {
	return (
		<div className="flex flex-col gap-8">
			{/* Header */}
			<div className="text-small text-text-dim">
				Step {step} of {totalSteps}
			</div>

			{/* Headline */}
			<h1
				className="text-4xl font-serif font-bold text-text"
				style={{ fontFamily: 'var(--font-serif)' }}
			>
				{headline}
			</h1>

			{/* Body */}
			{children && <div className="flex flex-col gap-4">{children}</div>}

			{/* Footer */}
			{footer && <div className="flex gap-4 pt-8">{footer}</div>}
		</div>
	);
}
