"use client";

import Fuse from "fuse.js";
import { useMemo, useState } from "react";
import Link from "next/link";
import type { Manifest, Page } from "@/lib/wiki/manifest";

export function WikiSearch({ manifest }: { manifest: Manifest }) {
  const [q, setQ] = useState("");
  const fuse = useMemo(() => new Fuse(manifest.pages, {
    keys: ["title", "headings.text"], threshold: 0.4,
  }), [manifest]);
  const results = q ? fuse.search(q).slice(0, 10).map((r) => r.item) : [];
  return (
    <div className="mb-4">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search wiki…"
        className="w-full px-3 py-2 rounded bg-muted text-foreground"
      />
      {results.length > 0 && (
        <ul className="mt-2 space-y-1">
          {results.map((p: Page) => (
            <li key={p.path}>
              <Link
                href={`/wiki/${p.path.replace(/\.md$/, "").replace(/\/index$/, "")}`}
                className="text-sm text-primary hover:underline"
              >{p.title}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
