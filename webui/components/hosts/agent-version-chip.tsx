import { Badge } from "@/components/ui/badge";

export function AgentVersionChip({
  current, latest, status,
}: {
  current?: string | null;
  latest?: string | null;
  status?: string | null;
}) {
  if (!current) return <Badge variant="outline">unknown</Badge>;
  const drift = latest && current !== latest;
  const updating = status && !["idle", "rolled_back"].includes(status);
  return (
    <Badge
      variant={updating ? "default" : drift ? "secondary" : "outline"}
      title={status ? `status: ${status}` : undefined}
    >
      {current}{drift && !updating && " ↑"}
      {updating && " …"}
    </Badge>
  );
}
