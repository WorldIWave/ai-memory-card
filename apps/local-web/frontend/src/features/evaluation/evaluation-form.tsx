// Input: 无 props（内部维护 topic/explanation 状态）
// Role: Evaluation 模块表单，提交 topic + explanation 后调用 AI 评估接口
// Note: 返回 5 个维度评分（mastery/concept/mechanism/boundary/misconception）
// Usage: <EvaluationForm />（嵌入 Evaluation 页或 Review 侧边评估对话框）
import { FormEvent, useState } from "react";

import { apiRequest } from "../../api/client";
import type { EvaluationRead } from "../../api/types";

export function EvaluationForm() {
  const [topic, setTopic] = useState("");
  const [explanation, setExplanation] = useState("");
  const [result, setResult] = useState<EvaluationRead | null>(null);
  const [errorText, setErrorText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorText("");

    try {
      const response = await apiRequest<EvaluationRead>("/api/evaluations", {
        method: "POST",
        body: {
          target_unit: { topic },
          learner_explanation: explanation,
          rubric_version: "v1",
        },
      });
      setResult(response);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Evaluation failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <label>
        Topic
        <input aria-label="Topic" value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="e.g. Transformer attention" required />
      </label>
      <label>
        Explanation
        <textarea aria-label="Explanation" value={explanation} onChange={(event) => setExplanation(event.target.value)} rows={6} required />
      </label>
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Evaluating..." : "Evaluate understanding"}
      </button>
      {errorText ? <p className="status-error">{errorText}</p> : null}
      {result ? (
        <section className="metric-grid" aria-live="polite">
          <p>Mastery: {result.mastery_score.toFixed(2)}</p>
          <p>Concept: {result.concept_score.toFixed(2)}</p>
          <p>Mechanism: {result.mechanism_score.toFixed(2)}</p>
          <p>Boundary: {result.boundary_score.toFixed(2)}</p>
          <p>Misconception: {result.misconception_score.toFixed(2)}</p>
        </section>
      ) : null}
    </form>
  );
}
