import type { Config } from 'tailwindcss';

const config: Config = {
	content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'],
	theme: {
		extend: {
			colors: {
				canvas: 'hsl(var(--canvas))',
				surface: 'hsl(var(--surface))',
				'surface-2': 'hsl(var(--surface-2))',
				hairline: 'hsl(var(--hairline))',
				text: 'hsl(var(--text))',
				'text-dim': 'hsl(var(--text-dim))',
				accent: 'hsl(var(--accent))',
				'accent-dim': 'hsl(var(--accent-dim))',
				warn: 'hsl(var(--warn))',
				danger: 'hsl(var(--danger))',
				ok: 'hsl(var(--ok))',
			},
			fontFamily: {
				display: 'var(--font-display)',
				heading: 'var(--font-heading)',
				body: 'var(--font-body)',
				mono: 'var(--font-mono)',
				serif: 'var(--font-serif)',
			},
			fontSize: {
				display: ['40px', { lineHeight: '1.2', fontWeight: '400' }],
				h1: ['32px', { lineHeight: '1.2', fontWeight: '400' }],
				h2: ['24px', { lineHeight: '1.3', fontWeight: '400' }],
				h3: ['18px', { lineHeight: '1.4', fontWeight: '500' }],
				body: ['14px', { lineHeight: '1.5', fontWeight: '400' }],
				small: ['12px', { lineHeight: '1.4', fontWeight: '500' }],
				'mono-readout': ['14px', { lineHeight: '1.5', fontWeight: '400' }],
				'mono-tiny': ['11px', { lineHeight: '1.3', fontWeight: '500' }],
				'docs-body': ['17px', { lineHeight: '1.7', fontWeight: '400' }],
			},
			spacing: {
				xs: '4px',
				sm: '8px',
				md: '12px',
				lg: '16px',
				xl: '20px',
				'2xl': '24px',
				'3xl': '32px',
				'4xl': '48px',
				'5xl': '64px',
			},
			borderRadius: {
				sm: '2px',
				md: '4px',
				lg: '6px',
			},
		},
	},
	plugins: [require('@tailwindcss/container-queries')],
};

export default config;
