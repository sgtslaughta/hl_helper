import { AgentReleaseList } from "@/components/settings/agent-release-list";

export default function AgentReleasesPage() {
  return (
    <div className="p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Agent Releases</h1>
        <p className="text-sm text-muted-foreground">Upload, manage, and yank agent binary releases.</p>
      </header>
      <AgentReleaseList />
    </div>
  );
}
