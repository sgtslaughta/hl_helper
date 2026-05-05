import { ShellShell } from '@/components/shell/shell-shell';

export const dynamic = 'force-dynamic';

export default function ShellLayout({ children }: { children: React.ReactNode }) {
	return <ShellShell>{children}</ShellShell>;
}
