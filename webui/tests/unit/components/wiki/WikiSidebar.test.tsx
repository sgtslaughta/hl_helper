import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WikiSidebar } from "@/components/wiki/WikiSidebar";
import type { Manifest } from "@/lib/wiki/manifest";

const m: Manifest = {
  generatedAt: "x",
  pages: [
    { path: "user-guide/getting-started/overview.md", title: "Overview", status: "stable", headings: [] },
    { path: "admin/operations/audit.md", title: "Audit", status: "planned", headings: [] },
  ],
};

describe("WikiSidebar", () => {
  it("renders page links grouped by section", () => {
    render(<WikiSidebar manifest={m} currentPath="user-guide/getting-started/overview.md" />);
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Audit")).toBeInTheDocument();
  });
  it("shows planned badge", () => {
    render(<WikiSidebar manifest={m} currentPath="" />);
    expect(screen.getByText(/planned/i)).toBeInTheDocument();
  });
});
