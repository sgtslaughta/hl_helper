'use client';

import { ShellShell } from '@/components/shell/shell-shell';

// ShellShell is a Client Component (`'use client'` at top of shell-shell.tsx)
// so it hydrates on every route under (shell)/. Importing directly is faster
// than dynamic({ ssr: false }) which split a redundant chunk and caused
// ChunkLoadError when the manifest revved during HMR.
export default function ShellLayout({ children }: { children: React.ReactNode }) {
	return <ShellShell>{children}</ShellShell>;
}
