'use client';

export const dynamic = 'force-dynamic';

import { useParams } from 'next/navigation';
import { MissionControlShell } from '@/components/hosts/mission-control/mission-control-shell';

export default function HostDetailPage() {
  const params = useParams<{ id: string }>();
  return <MissionControlShell initialHostId={params.id} />;
}
