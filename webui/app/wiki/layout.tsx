import { promises as fs } from "node:fs";
import path from "node:path";
import type { Manifest } from "@/lib/wiki/manifest";
import { WikiSidebar } from "@/components/wiki/WikiSidebar";
import { WikiSearch } from "@/components/wiki/WikiSearch";

async function loadManifest(): Promise<Manifest | null> {
  try {
    const p = path.join(process.cwd(), "public", "wiki", "index.json");
    return JSON.parse(await fs.readFile(p, "utf-8")) as Manifest;
  } catch {
    return null;
  }
}

export default async function WikiLayout({ children }: { children: React.ReactNode }) {
  const manifest = await loadManifest();
  if (!manifest) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold">Wiki not built</h1>
        <p className="text-muted-foreground">
          Run <code>npm run build:wiki</code> to generate the bundle.
        </p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[18rem_1fr] gap-6 p-6">
      <aside>
        <WikiSearch manifest={manifest} />
        <WikiSidebar manifest={manifest} currentPath="" />
      </aside>
      <main>{children}</main>
    </div>
  );
}
