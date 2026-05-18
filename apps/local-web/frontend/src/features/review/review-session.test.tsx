import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewSession } from "./review-session";

describe("ReviewSession", () => {
  it("renders markdown and latex in review cards", () => {
    const { container } = render(
      <ReviewSession
        card={{ id: 7, front: "What is $E=mc^2$?", back: "**Energy**", card_type: "recall" }}
      />,
    );

    expect(container.querySelector(".card-content-renderer")).not.toBeNull();
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("marks the flashcard for safe long-content rendering", () => {
    render(
      <ReviewSession
        card={{
          id: 4,
          front: "This is a very long prompt ".repeat(40),
          back: "A long answer ".repeat(30),
          card_type: "recall",
        }}
      />,
    );

    const flashcard = screen.getByRole("article", { name: /flashcard/i });
    expect(flashcard).toHaveClass("review-flashcard");
    expect(screen.getByText(/This is a very long prompt/)).toHaveClass("review-flashcard-prompt");
  });

  it("renders an accessible flashcard and submits a grade", async () => {
    const onGrade = vi.fn().mockResolvedValue(undefined);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is attention?",
          back: "A relevance weighting mechanism.",
          card_type: "recall",
        }}
        onGrade={onGrade}
      />,
    );

    const flashcard = screen.getByRole("article", { name: /flashcard/i });
    expect(flashcard).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /show answer/i })).not.toBeInTheDocument();
    fireEvent.click(flashcard);
    fireEvent.click(screen.getByRole("button", { name: /good/i }));

    await waitFor(() => expect(onGrade).toHaveBeenCalledWith("good"));
  });

  it("invokes onEdit from the review menu", async () => {
    const onEdit = vi.fn();

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is attention?",
          back: "A relevance weighting mechanism.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
        onEdit={onEdit}
      />,
    );

    const menuButton = screen.getByRole("button", { name: /menu/i });
    fireEvent.keyDown(menuButton, { key: "ArrowDown", code: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /edit card/i }));

    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it("opens the report dialog without submitting immediately", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is attention?",
          back: "A relevance weighting mechanism.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    const menuButton = screen.getByRole("button", { name: /menu/i });
    fireEvent.keyDown(menuButton, { key: "ArrowDown", code: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /report error/i }));

    expect(screen.getByRole("dialog", { name: /report card issue/i })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("evaluates first, then saves the returned result without evaluating again", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        mastery_score: 72,
        accuracy_score: 80,
        concept_score: 80,
        mechanism_score: 65,
        boundary_score: 55,
        misconception_score: 20,
        misconception_detected: false,
        confidence_score: 88,
        uncertain: false,
        feedback: "The core idea is mostly correct, but the mechanism is incomplete.",
        weak_points: ["mechanism", "boundary"],
        reinforcement_advice: ["Explain the penalty term."],
        rubric_version: "v1",
        provider_meta: { trace_id: "trace-1" },
        trace_id: "trace-1",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "It prevents overfitting by constraining the model." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^evaluate$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/evaluations"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"card_id":3'),
        }),
      ),
    );
    const [, request] = fetchMock.mock.calls[0] as [string, { body?: string }];
    expect(request.body).toContain('"target_unit":{"text":"What is regularization?"}');
    expect(request.body).toContain(
      '"learner_explanation":"It prevents overfitting by constraining the model."',
    );
    expect(await screen.findByText(/mastery/i)).toBeInTheDocument();
    expect(screen.getByText("80.00")).toBeInTheDocument();
    expect(screen.getByText(/mostly correct/i)).toBeInTheDocument();
    expect(screen.getByText(/mechanism, boundary/i)).toBeInTheDocument();
    expect(screen.getByText(/explain the penalty term/i)).toBeInTheDocument();
    expect(screen.getByText(/no misconception detected/i)).toBeInTheDocument();
    expect(screen.getByText(/confidence/i)).toBeInTheDocument();
    expect(screen.getByText("88.00")).toBeInTheDocument();
    expect(screen.getByText(/stable/i)).toBeInTheDocument();

    fetchMock.mockClear();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({
        id: "learning_event:1",
        event_type: "evaluation",
        created_at: "2026-05-09T00:00:00Z",
        summary: "Understanding evaluation saved",
        payload: {},
      }),
    });

    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/evaluations/records"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"mastery_score":72'),
        }),
      ),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog", { name: /self-assessment/i })).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("keeps the evaluation draft and shows an actionable message when the AI plugin is not configured", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        detail: "plugin_not_configured",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "It prevents overfitting by constraining the model." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^evaluate$/i }));

    expect(await screen.findByText(/configure the AI plugin/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("It prevents overfitting by constraining the model.")).toBeInTheDocument();
    expect(screen.queryByText("plugin_not_configured")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("keeps the evaluation draft when closing and reopening the dialog for the same card", async () => {
    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "Regularization constrains model behavior." },
    });
    fireEvent.click(screen.getByRole("button", { name: /minimize evaluation window/i }));

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));

    expect(screen.getByDisplayValue("Regularization constrains model behavior.")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog", { name: /self-assessment/i });
    expect(within(dialog).getByText("What is regularization?")).toBeInTheDocument();
    expect(within(dialog).getByText("It constrains the model to reduce overfitting.")).toBeInTheDocument();
  });

  it("supports minimizing, expanding, and clearing the evaluation dialog", async () => {
    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "Regularization constrains model behavior." },
    });

    const dialog = screen.getByRole("dialog", { name: /self-assessment/i });
    expect(dialog).toHaveClass("ui-dialog-content-evaluation");
    fireEvent.click(screen.getByRole("button", { name: /expand evaluation window/i }));
    expect(dialog).toHaveClass("is-expanded");

    fireEvent.click(screen.getByRole("button", { name: /minimize evaluation window/i }));
    expect(screen.queryByRole("dialog", { name: /self-assessment/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    expect(screen.getByDisplayValue("Regularization constrains model behavior.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close evaluation window/i }));
    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    expect(screen.queryByDisplayValue("Regularization constrains model behavior.")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/describe your understanding/i)).toHaveValue("");
  });

  it("shows an actionable message for generic provider request failures", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        detail: "provider_request_failed",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "It prevents overfitting by constraining the model." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^evaluate$/i }));

    expect(await screen.findByText(/AI provider request failed/i)).toBeInTheDocument();
    expect(screen.queryByText("provider_request_failed")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("shows an actionable message when the configured provider model is unavailable", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        detail: "provider_model_not_found",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "It prevents overfitting by constraining the model." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^evaluate$/i }));

    expect(await screen.findByText(/configured model is not available/i)).toBeInTheDocument();
    expect(screen.queryByText("provider_model_not_found")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("saves review notes through the dedicated note API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "note-1",
        event_type: "note",
        created_at: "2026-04-21T00:00:00Z",
        summary: "Note saved",
        payload: {},
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 7,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /self-assessment note/i }), {
      target: { value: "This needs another pass." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/7/notes"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"note":"This needs another pass."'),
        }),
      ),
    );
    const [, request] = fetchMock.mock.calls[0] as [string, { body?: string }];
    expect(request.body).toContain('"source":"review"');
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/review/submit"),
      expect.anything(),
    );
    await waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument());

    vi.unstubAllGlobals();
  });

  it("keeps the note dialog open and shows an error when note saving fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({
        detail: "Note save failed",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 7,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /self-assessment note/i }), {
      target: { value: "This needs another pass." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("dialog", { name: /self-assessment note/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue("This needs another pass.")).toBeInTheDocument();
    expect(screen.getByText(/note save failed/i)).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("keeps the next card note dialog open when an earlier note save resolves late", async () => {
    let resolveFirstNote: (value: {
      ok: true;
      status: 200;
      json: () => Promise<{
        id: string;
        event_type: string;
        created_at: string;
        summary: string;
        payload: Record<string, unknown>;
      }>;
    }) => void = () => {};

    const fetchMock = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFirstNote = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(
      <ReviewSession
        card={{
          id: 7,
          front: "Card A",
          back: "Answer A",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    fireEvent.change(screen.getByPlaceholderText(/note/i), {
      target: { value: "Card A note." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    rerender(
      <ReviewSession
        card={{
          id: 8,
          front: "Card B",
          back: "Answer B",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    fireEvent.change(screen.getByPlaceholderText(/note/i), {
      target: { value: "Card B note." },
    });

    await act(async () => {
      resolveFirstNote({
        ok: true,
        status: 200,
        json: async () => ({
          id: "note-1",
          event_type: "note",
          created_at: "2026-04-21T00:00:00Z",
          summary: "Note saved",
          payload: {},
        }),
      });
    });

    expect(screen.getByRole("dialog", { name: /self-assessment note/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Card B note.")).toBeInTheDocument();
    expect(screen.queryByText(/review submit failed/i)).not.toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("keeps a reopened note dialog open on the same card when an older save resolves late", async () => {
    let resolveFirstNote: (value: {
      ok: true;
      status: 200;
      json: () => Promise<{
        id: string;
        event_type: string;
        created_at: string;
        summary: string;
        payload: Record<string, unknown>;
      }>;
    }) => void = () => {};

    const fetchMock = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFirstNote = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 7,
          front: "Card A",
          back: "Answer A",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /self-assessment note/i }), {
      target: { value: "Draft A" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /self-assessment note/i }), {
      target: { value: "Draft B" },
    });

    await act(async () => {
      resolveFirstNote({
        ok: true,
        status: 200,
        json: async () => ({
          id: "note-1",
          event_type: "note",
          created_at: "2026-04-21T00:00:00Z",
          summary: "Note saved",
          payload: {},
        }),
      });
    });

    expect(screen.getByRole("dialog", { name: /self-assessment note/i })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /self-assessment note/i })).toHaveValue("Draft B");

    vi.unstubAllGlobals();
  });

  it("ignores late evaluation results after closing the dialog", async () => {
    let resolveFetch: (value: {
      ok: true;
      status: 200;
      json: () => Promise<{
        mastery_score: number;
        accuracy_score?: number;
        concept_score: number;
        mechanism_score: number;
        boundary_score: number;
        misconception_score: number;
        misconception_detected?: boolean;
        feedback?: string;
        weak_points?: string[];
        reinforcement_advice?: string[];
        rubric_version?: string;
        provider_meta?: Record<string, unknown>;
        trace_id: string;
      }>;
    }) => void = () => {};

    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise((resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is regularization?",
          back: "It constrains the model to reduce overfitting.",
          card_type: "recall",
        }}
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    fireEvent.change(screen.getByPlaceholderText(/describe your understanding/i), {
      target: { value: "It prevents overfitting by constraining the model." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^evaluate$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(request.signal).toBeInstanceOf(AbortSignal);

    fireEvent.click(screen.getByRole("button", { name: /close evaluation window/i }));
    expect(request.signal?.aborted).toBe(true);

    resolveFetch({
      ok: true,
      status: 200,
      json: async () => ({
        mastery_score: 0.95,
        accuracy_score: 0.9,
        concept_score: 0.9,
        mechanism_score: 0.85,
        boundary_score: 0.8,
        misconception_score: 0.75,
        misconception_detected: false,
        confidence_score: 80,
        uncertain: false,
        feedback: "Late feedback should not render.",
        weak_points: ["boundary"],
        reinforcement_advice: ["Late advice"],
        rubric_version: "v1",
        provider_meta: { trace_id: "trace-aborted" },
        trace_id: "trace-aborted",
      }),
    });

    await waitFor(() => expect(screen.queryByText(/mastery/i)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /self-assessment/i }));
    expect(screen.queryByText(/mastery/i)).not.toBeInTheDocument();
    expect(screen.queryByText("0.95")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("ignores shortcut keys when focus is inside form controls", () => {
    render(
      <ReviewSession
        card={{
          id: 3,
          front: "What is attention?",
          back: "A relevance weighting mechanism.",
          card_type: "recall",
        }}
      />,
    );

    const select = document.createElement("select");
    document.body.appendChild(select);
    fireEvent.keyDown(select, { code: "Space", key: " " });
    expect(screen.queryByText(/A relevance weighting mechanism/i)).not.toBeInTheDocument();
  });

  it("accepts grade shortcuts when focus remains on a regular button", async () => {
    const onGrade = vi.fn().mockResolvedValue(undefined);

    render(
      <ReviewSession
        card={{
          id: 10,
          front: "Keyboard target",
          back: "Keyboard answer",
          card_type: "recall",
        }}
        onGrade={onGrade}
      />,
    );

    fireEvent.click(screen.getByRole("article", { name: /flashcard/i }));

    const helperButton = document.createElement("button");
    helperButton.type = "button";
    helperButton.textContent = "helper";
    document.body.appendChild(helperButton);
    helperButton.focus();

    fireEvent.keyDown(helperButton, { key: "2", code: "Digit2" });

    await waitFor(() => expect(onGrade).toHaveBeenCalledWith("hard"));
    helperButton.remove();
  });

  it("accepts numpad shortcuts after the answer is revealed", async () => {
    const onGrade = vi.fn().mockResolvedValue(undefined);

    render(
      <ReviewSession
        card={{
          id: 11,
          front: "Numpad target",
          back: "Numpad answer",
          card_type: "recall",
        }}
        onGrade={onGrade}
      />,
    );

    fireEvent.click(screen.getByRole("article", { name: /flashcard/i }));
    fireEvent.keyDown(window, { key: "1", code: "Numpad1" });

    await waitFor(() => expect(onGrade).toHaveBeenCalledWith("again"));
  });
});
