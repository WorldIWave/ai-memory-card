import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { BookOpen } from "lucide-react";
import { describe, expect, it } from "vitest";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  MetricCard,
  SegmentedControl,
  Skeleton,
  StatusMessage,
} from ".";

describe("ui primitives", () => {
  it("renders accessible buttons and status messages", () => {
    render(
      <>
        <Button>Save</Button>
        <Button variant="danger">Delete</Button>
        <StatusMessage tone="error">Request failed</StatusMessage>
      </>,
    );

    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Request failed");
  });

  it("renders card, badge, metric, empty, and skeleton building blocks", () => {
    render(
      <>
        <Card>Panel content</Card>
        <Badge>recall</Badge>
        <MetricCard label="Reviewed today" value={12} />
        <EmptyState icon={BookOpen} title="No cards" description="Create your first card." />
        <Skeleton aria-label="Loading cards" />
      </>,
    );

    expect(screen.getByText("Panel content")).toBeInTheDocument();
    expect(screen.getByText("recall")).toBeInTheDocument();
    expect(screen.getByText("Reviewed today")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("12")).toHaveClass("ui-metric-value");
    expect(screen.getByText("No cards")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading cards")).toBeInTheDocument();
  });

  it("switches the active segmented control option", () => {
    function Harness() {
      const [rangeDays, setRangeDays] = useState<7 | 30>(7);

      return (
        <SegmentedControl
          label="Analytics range"
          value={rangeDays}
          options={[
            { value: 7, label: "7 days" },
            { value: 30, label: "30 days" },
          ]}
          onChange={setRangeDays}
        />
      );
    }

    render(<Harness />);

    expect(screen.getByRole("radiogroup", { name: "Analytics range" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "7 days" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "30 days" })).toHaveAttribute("aria-checked", "false");

    fireEvent.click(screen.getByRole("radio", { name: "30 days" }));

    expect(screen.getByRole("radio", { name: "7 days" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("radio", { name: "30 days" })).toHaveAttribute("aria-checked", "true");
  });

  it("moves selection and focus with the keyboard", () => {
    function Harness() {
      const [rangeDays, setRangeDays] = useState<7 | 30 | 90>(7);

      return (
        <SegmentedControl
          label="Analytics range"
          value={rangeDays}
          options={[
            { value: 7, label: "7 days" },
            { value: 30, label: "30 days" },
            { value: 90, label: "90 days" },
          ]}
          onChange={setRangeDays}
        />
      );
    }

    render(<Harness />);

    const first = screen.getByRole("radio", { name: "7 days" });
    const second = screen.getByRole("radio", { name: "30 days" });
    const third = screen.getByRole("radio", { name: "90 days" });

    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(second).toHaveFocus();
    expect(second).toHaveAttribute("aria-checked", "true");

    fireEvent.keyDown(second, { key: "End" });
    expect(third).toHaveFocus();
    expect(third).toHaveAttribute("aria-checked", "true");

    fireEvent.keyDown(third, { key: "ArrowLeft" });
    expect(second).toHaveFocus();
    expect(second).toHaveAttribute("aria-checked", "true");

    fireEvent.keyDown(second, { key: "Home" });
    expect(first).toHaveFocus();
    expect(first).toHaveAttribute("aria-checked", "true");
  });

  it("keeps one option tabbable when the current value is unmatched", () => {
    render(
      <SegmentedControl
        label="Analytics range"
        value={14 as 7 | 30}
        options={[
          { value: 7, label: "7 days" },
          { value: 30, label: "30 days" },
        ]}
        onChange={() => undefined}
      />,
    );

    expect(screen.getByRole("radio", { name: "7 days" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "30 days" })).toHaveAttribute("tabindex", "-1");
  });
});
