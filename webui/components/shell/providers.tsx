'use client';

import { createQueryClient } from '@/lib/query-cache';
import { QueryClientProvider } from '@tanstack/react-query';
import { NuqsAdapter } from 'nuqs/adapters/next/app';
import { Suspense, useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
	const [client] = useState(() => createQueryClient());
	return (
		<QueryClientProvider client={client}>
			<Suspense>
				<NuqsAdapter>{children}</NuqsAdapter>
			</Suspense>
		</QueryClientProvider>
	);
}
