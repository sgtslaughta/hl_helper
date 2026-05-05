'use client';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
	variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
	size?: 'sm' | 'md' | 'lg';
	isLoading?: boolean;
}

const variantStyles: Record<string, string> = {
	primary: 'bg-accent hover:bg-accent-dim text-canvas',
	secondary: 'bg-surface-2 hover:bg-hairline text-text',
	ghost: 'hover:bg-surface-2 text-text',
	danger: 'bg-danger hover:opacity-90 text-canvas',
};

const sizeStyles: Record<string, string> = {
	sm: 'px-2 py-1 text-xs',
	md: 'px-4 py-2 text-sm',
	lg: 'px-6 py-3 text-base',
};

export function Button({
	variant = 'primary',
	size = 'md',
	isLoading = false,
	disabled = false,
	className = '',
	children,
	type,
	...props
}: ButtonProps) {
	return (
		<button
			type={type ?? 'button'}
			disabled={disabled || isLoading}
			className={`inline-flex items-center justify-center rounded font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
			{...props}
		>
			{isLoading ? '...' : children}
		</button>
	);
}
