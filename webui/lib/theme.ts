'use client';

import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';

export function useThemeCustom() {
	const { theme, setTheme, systemTheme } = useTheme();
	const [mounted, setMounted] = useState(false);

	useEffect(() => {
		setMounted(true);
	}, []);

	const currentTheme = theme === 'system' ? systemTheme : theme;

	const setAccentColor = (color: 'cyan' | 'green' | 'orange' | 'oxblood' | 'violet'): void => {
		const colors: Record<string, { r: number; g: number; b: number }> = {
			cyan: { r: 0, g: 224, b: 255 },
			green: { r: 87, g: 217, b: 138 },
			orange: { r: 255, g: 176, b: 32 },
			oxblood: { r: 139, g: 36, b: 51 },
			violet: { r: 167, g: 107, b: 207 },
		};

		const c = colors[color];
		document.documentElement.style.setProperty('--accent', `${c.r} ${c.g} ${c.b}`);
	};

	return {
		theme: currentTheme,
		setTheme,
		mounted,
		setAccentColor,
	};
}
