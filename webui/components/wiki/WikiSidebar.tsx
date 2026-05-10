"use client";

import Link from "next/link";
import type { Manifest, Page } from "@/lib/wiki/manifest";

const SECTION_LABELS: Record<string, string> = {
  "user-guide": "User Guide",
  admin: "Administration",
  shared: "Reference",
};

function pageHref(p: Page): string {
  return `/wiki/${p.path.replace(/\.md$/, "").replace(/\/index$/, "")}`;
}

export interface WikiSidebarProps { manifest: Manifest; currentPath: string }

export function WikiSidebar({ manifest, currentPath }: WikiSidebarProps) {
  const groups = new Map<string, Page[]>();
  for (const p of manifest.pages) {
    const top = p.path.split("/")[0];
    if (!groups.has(top)) groups.set(top, []);
    groups.get(top)!.push(p);
  }
  return (
    <nav className="text-sm space-y-4">
      {[...groups.entries()].map(([section, pages]) => (
        <div key={section}>
          <h3 className="font-semibold mb-1">{SECTION_LABELS[section] ?? section}</h3>
          <ul className="space-y-1">
            {pages.map((p) => (
              <li key={p.path}>
                <Link
                  href={pageHref(p)}
                  className={p.path === currentPath ? "text-primary" : "text-muted-foreground hover:text-foreground"}
                >
                  {p.title}
                  {p.status !== "stable" && (
                    <span className={`ml-2 inline-block px-1.5 py-0.5 text-xs rounded ${
                      p.status === "planned" ? "bg-yellow-500/20 text-yellow-400" : "bg-gray-500/20 text-gray-400"
                    }`}>{p.status}</span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
