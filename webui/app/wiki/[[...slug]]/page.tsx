import { promises as fs } from "node:fs";
import path from "node:path";
import { notFound } from "next/navigation";
import { MarkdownView } from "@/components/wiki/MarkdownView";
import type { Manifest } from "@/lib/wiki/manifest";

const ROOT = path.join(process.cwd(), "public", "wiki");

async function loadManifest(): Promise<Manifest | null> {
  try {
    return JSON.parse(await fs.readFile(path.join(ROOT, "index.json"), "utf-8")) as Manifest;
  } catch {
    return null;
  }
}

async function loadPage(slug: string[] | undefined): Promise<string | null> {
  const m = await loadManifest();
  if (!m) return null;
  const target = (slug ?? []).join("/");
  const candidate =
    m.pages.find((p) => p.path === `${target}.md` || p.path === `${target}/index.md`)?.path ??
    (slug?.length ? null : "user-guide/getting-started/overview.md");
  if (!candidate) return null;
  try {
    return await fs.readFile(path.join(ROOT, candidate), "utf-8");
  } catch {
    return null;
  }
}

export default async function WikiPage({ params }: { params: Promise<{ slug?: string[] }> }) {
  const { slug } = await params;
  const md = await loadPage(slug);
  if (!md) notFound();
  return <MarkdownView source={md} />;
}
