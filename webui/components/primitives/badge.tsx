'use client';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
	variant?: 'default' | 'ok' | 'warn' | 'danger' | 'accent' | 'dim';
	size?: 'sm' | 'md' | 'lg';
	children: React.ReactNode;
}

const variantStyles: Record<string, string> = {
	default: 'bg-surface text-text',
	ok: 'bg-ok text-canvas',
	warn: 'bg-warn text-canvas',
	danger: 'bg-danger text-canvas',
	accent: 'bg-accent text-canvas',
	dim: 'bg-surface-2 text-text-dim',
};

const sizeStyles: Record<string, string> = {
	sm: 'px-2 py-0.5 text-xs',
	md: 'px-3 py-1 text-sm',
	lg: 'px-4 py-1.5 text-base',
};

export function Badge({
	variant = 'default',
	size = 'md',
	className = '',
	children,
	...props
}: BadgeProps) {
	return (
		<span
			className={`inline-flex items-center rounded font-medium ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
			{...props}
		>
			{children}
		</span>
	);
}
