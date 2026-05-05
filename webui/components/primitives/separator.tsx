'use client';

interface SeparatorProps extends React.HTMLAttributes<HTMLDivElement> {
	orientation?: 'horizontal' | 'vertical';
}

export function Separator({
	orientation = 'horizontal',
	className = '',
	...props
}: SeparatorProps) {
	return (
		<div
			{...props}
			className={`bg-hairline ${
				orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px'
			} ${className}`}
		/>
	);
}
