'use client';

import * as RadixTabs from '@radix-ui/react-tabs';

interface TabsProps {
	tabs: Array<{ label: string; value: string }>;
	children: React.ReactNode;
	defaultValue?: string;
	onValueChange?: (value: string) => void;
}

export function Tabs({ tabs, children, defaultValue, onValueChange }: TabsProps) {
	return (
		<RadixTabs.Root defaultValue={defaultValue ?? tabs[0]?.value} onValueChange={onValueChange}>
			<RadixTabs.List className="flex border-b border-hairline">
				{tabs.map(tab => (
					<RadixTabs.Trigger
						key={tab.value}
						value={tab.value}
						className="px-4 py-2 text-sm font-medium text-text-dim hover:text-text data-[state=active]:border-b-2 data-[state=active]:border-accent data-[state=active]:text-text"
					>
						{tab.label}
					</RadixTabs.Trigger>
				))}
			</RadixTabs.List>
			{children}
		</RadixTabs.Root>
	);
}

interface TabsContentProps {
	value: string;
	children: React.ReactNode;
}

export function TabsContent({ value, children }: TabsContentProps) {
	return (
		<RadixTabs.Content value={value} className="py-4">
			{children}
		</RadixTabs.Content>
	);
}
