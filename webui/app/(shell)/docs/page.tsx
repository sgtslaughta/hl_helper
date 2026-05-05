'use client';

import { EmptyState } from '@/components/empty-states/empty-state';
import { Button } from '@/components/primitives/button';
import { BookOpen, Code, Github } from 'lucide-react';
import Link from 'next/link';

export default function DocsPage() {
	return (
		<div className="flex flex-col gap-8 p-8">
			<div>
				<h1 className="text-2xl font-bold text-text">Documentation</h1>
				<p className="text-text-dim mt-2">Learn how to use HL Helper</p>
			</div>

			<div className="grid gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
				{/* Getting Started */}
				<div className="flex flex-col gap-4 rounded border border-hairline bg-surface p-6">
					<BookOpen className="h-6 w-6 text-accent" />
					<div>
						<h3 className="font-semibold text-text">Getting Started</h3>
						<p className="text-small text-text-dim mt-1">Learn the basics and get up and running</p>
					</div>
					<Button variant="secondary" size="sm" type="button">
						Read Guide
					</Button>
				</div>

				{/* API Reference */}
				<div className="flex flex-col gap-4 rounded border border-hairline bg-surface p-6">
					<Code className="h-6 w-6 text-accent" />
					<div>
						<h3 className="font-semibold text-text">API Reference</h3>
						<p className="text-small text-text-dim mt-1">Complete API documentation and examples</p>
					</div>
					<Link href="/docs/api">
						<Button variant="secondary" size="sm" type="button">
							View API
						</Button>
					</Link>
				</div>

				{/* GitHub */}
				<div className="flex flex-col gap-4 rounded border border-hairline bg-surface p-6">
					<Github className="h-6 w-6 text-accent" />
					<div>
						<h3 className="font-semibold text-text">GitHub</h3>
						<p className="text-small text-text-dim mt-1">Source code and issue tracking</p>
					</div>
					<Button variant="secondary" size="sm" type="button">
						Open GitHub
					</Button>
				</div>
			</div>

			{/* Full MDX placeholder */}
			<EmptyState
				title="Full Documentation"
				description="Comprehensive guides and tutorials coming soon"
				icon={<BookOpen className="h-12 w-12" />}
			/>
		</div>
	);
}
