#!/usr/bin/env tsx
/**
 * Build webui/public/wiki/ from docs/{user-guide,admin,shared}.
 * Emits markdown copies + index.json manifest used by /wiki route.
 */
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(__dirname, "..");
const SRC_DIRS = ["docs/user-guide", "docs/admin", "docs/shared"];
const OUT = path.join(ROOT, "webui/public/wiki");

interface Frontmatter { title: string; status: string; [k: string]: unknown }
interface Entry { path: string; title: string; status: string; headings: { level: number; text: string; slug: string }[] }

const FM_RE = /^---\n([\s\S]*?)\n---\n/;
const HEADING_RE = /^(#{1,6})\s+(.+?)\s*$/gm;

function parseFrontmatter(text: string): { fm: Frontmatter; body: string } {
  const m = text.match(FM_RE);
  if (!m) return { fm: { title: "Untitled", status: "stable" }, body: text };
  const fm: Frontmatter = { title: "Untitled", status: "stable" };
  for (const line of m[1].split("\n")) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const k = line.slice(0, idx).trim();
    const v = line.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    fm[k] = v;
  }
  return { fm, body: text.slice(m[0].length) };
}

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^\w]+/g, "-").replace(/^-|-$/g, "");
}

function extractHeadings(body: string) {
  const out: Entry["headings"] = [];
  for (const m of body.matchAll(HEADING_RE)) {
    out.push({ level: m[1].length, text: m[2], slug: slugify(m[2]) });
  }
  return out;
}

function walk(dir: string, base: string): Entry[] {
  if (!fs.existsSync(dir)) return [];
  const entries: Entry[] = [];
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) {
      entries.push(...walk(full, base));
    } else if (name.endsWith(".md")) {
      const rel = path.relative(base, full);
      const text = fs.readFileSync(full, "utf-8");
      const { fm, body } = parseFrontmatter(text);
      entries.push({
        path: rel.replace(/\\/g, "/"),
        title: fm.title,
        status: fm.status,
        headings: extractHeadings(body),
      });
      const dst = path.join(OUT, rel);
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(full, dst);
    }
  }
  return entries;
}

function main() {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const pages: Entry[] = [];
  for (const src of SRC_DIRS) {
    pages.push(...walk(path.join(ROOT, src), path.join(ROOT, "docs")));
  }
  const manifest = {
    generatedAt: new Date().toISOString(),
    pages: pages.sort((a, b) => a.path.localeCompare(b.path)),
  };
  fs.writeFileSync(path.join(OUT, "index.json"), JSON.stringify(manifest, null, 2));
  console.log(`wiki: ${pages.length} pages → ${OUT}`);
}

main();
