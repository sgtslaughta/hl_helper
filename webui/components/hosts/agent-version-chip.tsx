import { Badge } from "@/components/primitives/badge";

export function AgentVersionChip({
  current, latest, status,
}: {
  current?: string | null;
  latest?: string | null;
  status?: string | null;
}) {
  if (!current) return <Badge variant="dim">unknown</Badge>;
  const drift = latest && current !== latest;
  const updating = status && !["idle", "rolled_back"].includes(status);
  return (
    <Badge
      variant={updating ? "accent" : drift ? "warn" : "dim"}
      title={status ? `status: ${status}` : undefined}
    >
      {current}{drift && !updating && " ↑"}
      {updating && " …"}
    </Badge>
  );
}
