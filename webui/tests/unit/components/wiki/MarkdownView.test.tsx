import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownView } from "@/components/wiki/MarkdownView";

describe("MarkdownView", () => {
  it("renders headings and paragraphs", () => {
    render(<MarkdownView source={"# Title\n\nHello world."} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Title");
    expect(screen.getByText("Hello world.")).toBeInTheDocument();
  });
  it("renders code blocks", () => {
    render(<MarkdownView source={"```js\nconsole.log(1)\n```"} />);
    expect(screen.getByText("console")).toBeInTheDocument();
  });
  it("strips YAML frontmatter from output", () => {
    render(<MarkdownView source={"---\ntitle: X\nstatus: stable\n---\n\nBody."} />);
    expect(screen.queryByText(/title: X/)).not.toBeInTheDocument();
    expect(screen.getByText("Body.")).toBeInTheDocument();
  });
});
