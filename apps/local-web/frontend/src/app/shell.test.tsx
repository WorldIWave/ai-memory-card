import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("AppShell", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
  });

  it("renders the refreshed workspace navigation with accessible language switch", async () => {
    await import("../i18n");
    const { AppShell } = await import("./shell");

    render(
      <MemoryRouter initialEntries={["/library"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/library" element={<main>Library content</main>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("complementary", { name: /AI Memory Card/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /牌库|library/i })).toHaveClass("is-active");
    expect(screen.getByRole("button", { name: /切换语言|switch language/i })).toBeInTheDocument();
    expect(screen.getByText("Library content")).toBeInTheDocument();
  });
});
