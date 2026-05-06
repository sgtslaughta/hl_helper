'use client';

export const dynamic = 'force-dynamic';

import { MissionControlShell } from '@/components/hosts/mission-control/mission-control-shell';

export default function HostsPage() {
  return <MissionControlShell initialHostId={null} />;
}
