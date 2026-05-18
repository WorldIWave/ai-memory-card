// Input: Mock fetch（返回 mastery_score 等评测结果）  |  Output: 断言分数渲染到 DOM
// Role: 单元测试 EvaluationForm 组件，验证表单提交后正确展示 AI 评测掌握度分数
// Note: 使用 vi.stubGlobal 拦截全局 fetch，测试后调用 unstubAllGlobals 恢复环境
// Usage: vitest run src/features/evaluation/evaluation-form.test.tsx，无需真实后端
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EvaluationForm } from "./evaluation-form";

describe("EvaluationForm", () => {
  it("shows the returned mastery score after submit", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        mastery_score: 0.75,
        concept_score: 2,
        mechanism_score: 2,
        boundary_score: 1,
        misconception_score: 3,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EvaluationForm />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: "Transformer" },
    });
    fireEvent.change(screen.getByLabelText(/explanation/i), {
      target: { value: "A sequence model based on self-attention." },
    });
    fireEvent.submit(screen.getByRole("button", { name: /evaluate understanding/i }).closest("form")!);

    await waitFor(() => expect(screen.getByText(/0.75/)).toBeInTheDocument());
    vi.unstubAllGlobals();
  });
});
