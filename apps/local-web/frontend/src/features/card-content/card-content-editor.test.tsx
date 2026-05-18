import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CardContentEditor } from "./card-content-editor";

describe("CardContentEditor", () => {
  it("inserts inline math at the cursor", () => {
    const onChange = vi.fn();
    render(<CardContentEditor label="Front" value="Energy" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /insert inline math/i }));

    expect(onChange).toHaveBeenCalledWith("Energy $x$");
  });

  it("inserts block math", () => {
    const onChange = vi.fn();
    render(<CardContentEditor label="Back" value="" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /insert block math/i }));

    expect(onChange).toHaveBeenCalledWith("$$\n\n$$");
  });

  it("shows a rendered preview", () => {
    render(<CardContentEditor label="Front" value="**Bold**" onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /preview/i }));

    expect(screen.getByText("Bold")).toHaveClass("font-semibold");
  });

  it("uploads pasted image and inserts returned markdown", async () => {
    const onChange = vi.fn();
    const uploadImage = vi.fn().mockResolvedValue({
      markdown: "![image](/api/assets/cards/drafts/draft_1/image.png)",
    });
    render(
      <CardContentEditor
        label="Front"
        value="Before"
        onChange={onChange}
        uploadImage={uploadImage}
      />,
    );

    const file = new File(["png"], "image.png", { type: "image/png" });
    fireEvent.paste(screen.getByLabelText("Front"), {
      clipboardData: {
        items: [
          {
            kind: "file",
            type: "image/png",
            getAsFile: () => file,
          },
        ],
      },
    });

    await waitFor(() => expect(uploadImage).toHaveBeenCalledWith(file));
    expect(onChange).toHaveBeenLastCalledWith("Before\n\n![image](/api/assets/cards/drafts/draft_1/image.png)");
  });
});
