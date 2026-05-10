export interface Heading { level: number; text: string; slug: string }
export interface Page { path: string; title: string; status: "stable" | "partial" | "planned"; headings: Heading[] }
export interface Manifest { generatedAt: string; pages: Page[] }
export interface TreeNode { section: string; pages: Page[]; subsections: TreeNode[] }

let cache: Manifest | null = null;

export async function loadManifest(): Promise<Manifest> {
  if (cache) return cache;
  const res = await fetch("/wiki/index.json");
  if (!res.ok) throw new Error(`wiki manifest: HTTP ${res.status}`);
  cache = (await res.json()) as Manifest;
  return cache;
}

export function getPage(m: Manifest, slug: string[]): Page | undefined {
  if (slug.length === 0) return undefined;
  const target = slug.join("/");
  return m.pages.find(
    (p) => p.path === `${target}.md` || p.path === `${target}/index.md`,
  );
}

export function buildTree(m: Manifest): TreeNode[] {
  const sections = new Map<string, Page[]>();
  for (const p of m.pages) {
    const top = p.path.split("/")[0];
    if (!sections.has(top)) sections.set(top, []);
    sections.get(top)!.push(p);
  }
  return [...sections.entries()].map(([section, pages]) => ({ section, pages, subsections: [] }));
}
