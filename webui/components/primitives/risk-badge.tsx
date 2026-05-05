import type { HTMLAttributes } from 'react';

export type RiskClass = 'info' | 'caution' | 'destructive' | 'irreversible';

const VARIANTS: Record<RiskClass, { label: string; className: string }> = {
  info: { label: 'Info', className: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  caution: { label: 'Caution', className: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30' },
  destructive: { label: 'Destructive', className: 'bg-orange-500/10 text-orange-400 border-orange-500/30' },
  irreversible: { label: 'Irreversible', className: 'bg-red-500/15 text-red-400 border-red-500/40' },
};

interface Props extends HTMLAttributes<HTMLSpanElement> {
  variant: RiskClass;
}

export function RiskBadge({ variant, className, ...rest }: Props) {
  const v = VARIANTS[variant];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${v.className} ${className ?? ''}`}
      {...rest}
    >
      {v.label}
    </span>
  );
}
