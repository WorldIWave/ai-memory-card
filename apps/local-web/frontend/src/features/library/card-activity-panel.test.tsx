import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardActivityPanel } from "./card-activity-panel";

describe("CardActivityPanel", () => {
  it("renders merged activity rows newest first", () => {
    render(
      <CardActivityPanel
        items={[
          {
            id: "evaluation:2",
            event_type: "evaluation",
            created_at: "2026-04-21T09:02:00Z",
            summary: "Mastery 0.8",
            payload: {},
          },
          {
            id: "review:1",
            event_type: "review",
            created_at: "2026-04-21T09:00:00Z",
            summary: "Good - next in 4 days",
            payload: {},
          },
        ]}
        isLoading={false}
        errorText=""
      />,
    );

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Mastery 0.8");
    expect(rows[1]).toHaveTextContent("Good - next in 4 days");
  });
});
