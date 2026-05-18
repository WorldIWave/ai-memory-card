import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardContentRenderer } from "./card-content-renderer";

describe("CardContentRenderer", () => {
  it("renders markdown emphasis and lists", () => {
    render(<CardContentRenderer content={"**Important**\n\n- one\n- two"} />);

    expect(screen.getByText("Important")).toHaveClass("font-semibold");
    expect(screen.getByText("one")).toBeInTheDocument();
    expect(screen.getByText("two")).toBeInTheDocument();
  });

  it("renders inline and block latex through katex", () => {
    const { container } = render(
      <CardContentRenderer content={"Inline $E=mc^2$\n\n$$\\frac{1}{2}$$"} />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.textContent).toContain("E");
  });

  it("renders markdown images with alt text", () => {
    render(<CardContentRenderer content={"![diagram](/api/assets/cards/drafts/demo/image.png)"} />);

    const image = screen.getByRole("img", { name: "diagram" });
    expect(image).toHaveAttribute("src", "/api/assets/cards/drafts/demo/image.png");
  });

  it("does not execute raw html", () => {
    render(<CardContentRenderer content={'<img src=x onerror="window.bad=true" />'} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/<img src=x/i)).toBeInTheDocument();
  });
});
