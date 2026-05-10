import { describe, it, expect, vi } from "vitest";
import { loadManifest, getPage, buildTree } from "../../../../lib/wiki/manifest";

const sample = {
  generatedAt: "2026-05-09T00:00:00Z",
  pages: [
    { path: "user-guide/getting-started/overview.md", title: "Overview", status: "stable", headings: [] },
    { path: "admin/operations/audit.md", title: "Audit", status: "stable", headings: [] },
  ],
};

describe("manifest", () => {
  it("loads JSON manifest", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => sample } as unknown as Response);
    const m = await loadManifest();
    expect(m.pages).toHaveLength(2);
  });
  it("getPage finds by slug path", () => {
    const p = getPage(sample as any, ["user-guide", "getting-started", "overview"]);
    expect(p?.title).toBe("Overview");
  });
  it("buildTree groups by top section", () => {
    const tree = buildTree(sample as any);
    expect(tree.map((s) => s.section).sort()).toEqual(["admin", "user-guide"]);
  });
});
