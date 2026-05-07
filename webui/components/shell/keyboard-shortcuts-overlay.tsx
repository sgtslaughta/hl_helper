'use client';

import { type HotkeyBinding, getHotkeys, ignoreEventInInputs } from '@/lib/hotkeys';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useState } from 'react';
import { useHotkeys } from 'react-hotkeys-hook';

export function KeyboardShortcutsOverlay() {
	const [open, setOpen] = useState(false);

	useHotkeys('?', () => setOpen(true), {
		preventDefault: true,
		ignoreEventWhen: ignoreEventInInputs,
	});
	useHotkeys('esc', () => setOpen(false), { preventDefault: true });

	const hotkeys = getHotkeys();
	const grouped = hotkeys.reduce(
		(acc, hotkey) => {
			if (!acc[hotkey.category]) {
				acc[hotkey.category] = [];
			}
			acc[hotkey.category].push(hotkey);
			return acc;
		},
		{} as Record<string, HotkeyBinding[]>,
	);

	const categoryTitles: Record<string, string> = {
		navigation: 'Navigation',
		action: 'Actions',
		ui: 'UI',
	};

	return (
		<Dialog.Root open={open} onOpenChange={setOpen}>
			<Dialog.Content className="fixed inset-0 flex items-center justify-center bg-black/50">
				<div className="w-full max-w-2xl rounded-lg border border-hairline bg-surface p-6 shadow-lg max-h-[90vh] overflow-auto">
					<div className="flex items-center justify-between mb-6">
						<h2 className="text-h2 text-text">Keyboard Shortcuts</h2>
						<button
							type="button"
							onClick={() => setOpen(false)}
							className="rounded p-1 hover:bg-surface-2 text-text-dim hover:text-text"
						>
							<X size={20} />
						</button>
					</div>

					<div className="space-y-6">
						{Object.entries(grouped).map(([category, bindings]) => (
							<div key={category}>
								<h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-dim">
									{categoryTitles[category] || category}
								</h3>
								<div className="space-y-2">
									{bindings.map(binding => (
										<div
											key={binding.keys}
											className="flex items-center justify-between rounded bg-surface-2 p-3"
										>
											<p className="text-sm text-text">{binding.description}</p>
											<kbd className="font-mono text-xs bg-surface px-2 py-1 rounded border border-hairline text-text-dim">
												{binding.keys}
											</kbd>
										</div>
									))}
								</div>
							</div>
						))}
					</div>

					<div className="mt-6 pt-6 border-t border-hairline">
						<p className="text-xs text-text-dim">
							Press <kbd className="font-mono px-1">?</kbd> to show shortcuts anytime
						</p>
					</div>
				</div>
			</Dialog.Content>
		</Dialog.Root>
	);
}
