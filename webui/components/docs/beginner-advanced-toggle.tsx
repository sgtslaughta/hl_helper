'use client';

import { Button } from '@/components/primitives/button';
import { useDocsModeStore } from '@/stores/docs-mode';

export function BeginnerAdvancedToggle() {
	const mode = useDocsModeStore(s => s.mode);
	const setMode = useDocsModeStore(s => s.setMode);

	return (
		<div className="flex gap-2">
			<Button
				variant={mode === 'beginner' ? 'primary' : 'secondary'}
				size="sm"
				onClick={() => setMode('beginner')}
				type="button"
			>
				Beginner
			</Button>
			<Button
				variant={mode === 'advanced' ? 'primary' : 'secondary'}
				size="sm"
				onClick={() => setMode('advanced')}
				type="button"
			>
				Advanced
			</Button>
		</div>
	);
}
