"use client";
import { useState } from "react";
import { Button } from "@/components/primitives/button";
import { Input } from "@/components/primitives/input";
import { mutate } from "swr";

export function AgentReleaseUpload() {
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="flex flex-wrap gap-4 items-end p-4 border border-hairline rounded-md bg-surface-2"
      onSubmit={async e => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        setBusy(true);
        try {
          const r = await fetch("/v1/agent-releases", { method: "POST", body: fd });
          if (!r.ok) throw new Error(await r.text());
          await mutate("/v1/agent-releases");
          (e.target as HTMLFormElement).reset();
        } finally { setBusy(false); }
      }}
    >
      <Input type="file" name="binary" label="Binary" required />
      <Input name="version" label="Version" placeholder="0.4.2" required />
      <div className="flex flex-col gap-2">
        <label htmlFor="channel-select" className="text-small font-semibold text-text">Channel<span className="text-danger">*</span></label>
        <select id="channel-select" name="channel" className="rounded border border-hairline bg-surface px-3 py-2 text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-accent" required>
          <option>stable</option>
          <option>beta</option>
          <option>canary</option>
        </select>
      </div>
      <div className="flex flex-col gap-2">
        <label htmlFor="os-select" className="text-small font-semibold text-text">OS<span className="text-danger">*</span></label>
        <select id="os-select" name="os" className="rounded border border-hairline bg-surface px-3 py-2 text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-accent" required>
          <option>linux</option>
          <option>darwin</option>
        </select>
      </div>
      <div className="flex flex-col gap-2">
        <label htmlFor="arch-select" className="text-small font-semibold text-text">Arch<span className="text-danger">*</span></label>
        <select id="arch-select" name="arch" className="rounded border border-hairline bg-surface px-3 py-2 text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-accent" required>
          <option>amd64</option>
          <option>arm64</option>
          <option>armv7</option>
        </select>
      </div>
      <Button type="submit" disabled={busy} variant="primary">{busy ? "Uploading…" : "Upload"}</Button>
    </form>
  );
}
