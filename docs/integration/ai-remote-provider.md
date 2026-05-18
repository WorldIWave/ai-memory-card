# Remote AI Provider Integration

Audience: developers building the remote AI service for AI Memory Card.

This document describes the current, required HTTP contract between the local app and a remote AI service. It is intentionally narrow: the first integration target is explanation evaluation. Card generation, card rewriting, and AI-driven scheduling are future extension points and are not required for the first service implementation.

## 1. Ownership Boundary

The local app owns:

- folders, decks, cards, review sessions, review scheduling, undo, and local persistence;
- all SQLite data, including `review_log` and `learning_event`;
- frontend UX and local API routes under `/api/*`;
- fallback behavior when no AI service is configured.

The remote AI service owns:

- receiving a learner explanation and target knowledge unit;
- scoring the explanation;
- returning structured scores and trace metadata;
- never mutating local cards, review state, or learning history directly.

The AI service is optional. The app must remain fully usable when the remote service is not configured or temporarily unavailable.

## 2. Current Local Pipeline

### Review-page evaluation

1. The user opens a card in the Review page.
2. The user opens the evaluation dialog and submits an explanation.
3. The frontend calls local `POST /api/evaluations`.
4. The local backend validates `card_id` when provided.
5. `EvaluationService` selects a provider:
   - `RemoteHTTPAIProvider` when `LMCA_AI_PROVIDER_BASE_URL` is configured;
   - `NoopAIProvider` when no base URL is configured.
6. `RemoteHTTPAIProvider` calls the remote AI service:
   - `POST {base_url}/v1/evaluations/explanation`
7. The local backend maps the remote response into `EvaluationRead`.
8. If `card_id` was provided, the backend writes a `learning_event` with `event_type="evaluation"`.
9. Review scheduling is not changed by evaluation results.

### Settings connectivity test

The Settings page can call local `POST /api/settings/test-ai-provider` with a candidate `base_url`. This test calls the same remote endpoint with a small sample payload. It does not persist the provider URL.

## 3. Required Remote Endpoint

### `POST /v1/evaluations/explanation`

The local backend calls this endpoint on the configured base URL.

Example:

```text
LMCA_AI_PROVIDER_BASE_URL=http://127.0.0.1:9000
Remote endpoint called by local backend:
POST http://127.0.0.1:9000/v1/evaluations/explanation
```

Required behavior:

- Accept JSON request bodies.
- Return JSON response bodies.
- Complete quickly. The current local HTTP client uses the default `httpx.Client` timeout, so the service should target responses under 5 seconds for first integration.
- Return a stable `trace_id` in `provider_meta` whenever possible.
- Treat unknown request fields as forward-compatible and ignore them.

Authentication:

- The current local adapter does not send authentication headers.
- If authentication is needed, coordinate a contract update before implementation.

## 4. Request Schema

Current request body sent by the local adapter:

```json
{
  "target_unit": {
    "text": "What is regularization?"
  },
  "learner_explanation": "It adds constraints to prevent overfitting.",
  "reference_material": null
}
```

Fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `target_unit` | object | yes | Free-form target knowledge unit. Current Review UI usually sends `{ "text": card.front }`. |
| `learner_explanation` | string | yes | The learner's submitted explanation. |
| `reference_material` | string or null | no | Optional reference text. Current Review UI usually omits it or sends `null`. |

Important compatibility note:

- The local `/api/evaluations` request schema already has `rubric_version`, defaulting to `"v1"`.
- The current `RemoteHTTPAIProvider` does not yet forward `rubric_version` to the remote service.
- Remote services should default to rubric version `v1` when the field is absent.

Recommended future-tolerant request handling:

```json
{
  "schema_version": "v1",
  "target_unit": {
    "text": "What is regularization?",
    "card_type": "recall",
    "tags": ["machine-learning"]
  },
  "learner_explanation": "It adds constraints to prevent overfitting.",
  "reference_material": "Regularization reduces overfitting by penalizing overly complex models.",
  "rubric_version": "v1"
}
```

The first implementation only needs to support the current request body. The future-tolerant fields above are listed so the remote service can avoid rejecting harmless additions later.

## 5. Response Schema

Required response body:

```json
{
  "mastery_score": 0.67,
  "dimension_scores": {
    "concept": 0.8,
    "mechanism": 0.6,
    "boundary": 0.5,
    "misconception": 0.2
  },
  "weak_points": [
    "Boundary conditions are not explained."
  ],
  "reinforcement_advice": [
    "Review when regularization helps and when it does not."
  ],
  "provider_meta": {
    "provider_name": "example-ai",
    "model_name": "example-model",
    "model_version": "2026-04-24",
    "prompt_version": "eval-v1",
    "rubric_version": "v1",
    "latency_ms": 420,
    "trace_id": "eval-20260424-0001"
  }
}
```

Fields consumed by the current local app:

| Remote field | Required | Local mapped field |
| --- | --- | --- |
| `mastery_score` | yes | `mastery_score` |
| `dimension_scores.concept` | recommended | `concept_score` |
| `dimension_scores.mechanism` | recommended | `mechanism_score` |
| `dimension_scores.boundary` | recommended | `boundary_score` |
| `dimension_scores.misconception` | recommended | `misconception_score` |
| `provider_meta.trace_id` | recommended | `trace_id` |

Fields accepted but not currently surfaced prominently:

- `weak_points`
- `reinforcement_advice`
- other `provider_meta` fields

Score scale:

- Recommended scale for all scores is `0.0` to `1.0`.
- The current local app does not enforce ranges and will display whatever numeric value the remote service returns.
- Use `misconception` as a risk score: higher means more misconception risk.

Fallback defaults in the local adapter:

- Missing `mastery_score` maps to `0.0`.
- Missing dimension scores map to `0.0`.
- Missing `provider_meta.trace_id` maps to `null`.

## 6. Error Contract

Recommended remote error response:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "learner_explanation is required",
    "trace_id": "eval-20260424-0002"
  }
}
```

Recommended status codes:

| Status | Meaning |
| --- | --- |
| `200` | Evaluation succeeded. |
| `400` | Request shape is invalid. |
| `422` | Request is syntactically valid but semantically unusable. |
| `429` | Provider rate limit or quota exceeded. |
| `500` | Unexpected provider failure. |
| `503` | Provider temporarily unavailable. |

Current local behavior:

- Any non-2xx response raises an HTTP client error in the local backend.
- The frontend will show an evaluation error and the user can continue reviewing.
- Failed evaluations do not mutate review state.

## 7. Local API Reference

### `POST /api/evaluations`

This is the local endpoint called by the frontend. Remote AI developers do not implement it, but it is useful for understanding the payload entering the provider layer.

Request:

```json
{
  "card_id": 123,
  "target_unit": {
    "text": "What is regularization?"
  },
  "learner_explanation": "It adds constraints to prevent overfitting.",
  "reference_material": null,
  "rubric_version": "v1"
}
```

Response:

```json
{
  "mastery_score": 0.67,
  "concept_score": 0.8,
  "mechanism_score": 0.6,
  "boundary_score": 0.5,
  "misconception_score": 0.2,
  "trace_id": "eval-20260424-0001"
}
```

Persistence:

- If `card_id` is present and valid, the local backend stores the result in `learning_event`.
- If `card_id` is missing, the evaluation can still run, but no card activity event is written.
- Evaluations never create `review_log` entries.

### `POST /api/settings/test-ai-provider`

Local Settings page smoke test endpoint.

Request:

```json
{
  "base_url": "http://127.0.0.1:9000"
}
```

Behavior:

- The local backend calls `POST {base_url}/v1/evaluations/explanation`.
- The test uses:

```json
{
  "target_unit": {
    "topic": "test"
  },
  "learner_explanation": "test"
}
```

Response on success:

```json
{
  "ok": true,
  "ai_provider": "remote_http",
  "result": {
    "mastery_score": 0.0,
    "concept_score": 0.0,
    "mechanism_score": 0.0,
    "boundary_score": 0.0,
    "misconception_score": 0.0,
    "trace_id": "eval-20260424-0003"
  }
}
```

## 8. Local Configuration

Development/backend environment variable:

```powershell
$env:LMCA_AI_PROVIDER_BASE_URL = "http://127.0.0.1:9000"
```

Then start the backend:

```powershell
cd apps/local-web/backend
uvicorn app.main:app --reload
```

Desktop packaged mode:

- The same environment variable can configure the backend process when launching from a controlled environment.
- Productized provider persistence is not implemented yet.
- Settings currently tests a candidate URL but does not save it.

## 9. Compatibility Rules

- Keep the remote API versioned under `/v1`.
- Do not assume local database IDs are globally meaningful.
- Do not require the remote service to know deck, review session, or scheduler state.
- Do not mutate cards or scheduling from evaluation results.
- Return best-effort metadata for observability, especially `trace_id`.
- Be permissive about unknown request fields.
- Keep response fields backward compatible once the first integration is accepted.

## 10. Not In Scope For First Integration

The following capabilities are intentionally not required for the first remote service:

- AI card generation.
- AI card rewriting.
- AI cloze generation.
- AI-driven review scheduling.
- Long-running async AI jobs.
- Direct local database access.
- Authentication and user accounts.

## 11. Future Extension Points

Likely future remote endpoints:

```text
POST /v1/knowledge/extract
POST /v1/rag/cards/generate
POST /v1/cards/generate
POST /v1/cards/rewrite
POST /v1/scheduling/suggest
```

`/v1/rag/cards/generate` is the first implemented generation bridge and is
documented below. The other endpoints remain roadmap items until the product
shape and data contract are finalized.

## 12. RAG Card Generation Integration

The local backend now has a local bridge endpoint for the first synchronous RAG
card generation flow:

```text
POST /api/ai/rag/import-cards
```

The frontend should read uploaded files into text and send:

```json
{
  "deck_name": "Machine Learning",
  "documents": [
    {
      "filename": "regularization.md",
      "content_type": "text/markdown",
      "text": "Regularization reduces overfitting..."
    }
  ],
  "topics": ["Regularization"],
  "generation_prefs": {
    "backend": "extractive",
    "card_types": ["recall", "understanding", "boundary"],
    "max_cards_per_unit": 3,
    "language": "en"
  }
}
```

Local backend behavior:

1. `RAGImportService` calls remote `POST /v1/rag/cards/generate`.
2. The remote response's `deck` and `cards` are converted to the existing JSON
   import payload shape.
3. `ImportService` creates the local deck, cards, and review states.
4. The local response returns imported `deck`, imported `cards`,
   `knowledge_units`, `warnings`, and `provider_meta`.

The remote service still never mutates the local database directly. The local
backend remains the only writer of decks, cards, and review state.

## 13. First Integration Checklist

Remote AI side:

- Implement `POST /v1/evaluations/explanation`.
- Accept the current minimal request body.
- Return `mastery_score`.
- Return `dimension_scores` with `concept`, `mechanism`, `boundary`, and `misconception`.
- Return `provider_meta.trace_id`.
- Keep typical latency under 5 seconds.
- Return useful JSON errors for invalid input and provider failures.

Local app side:

- Configure `LMCA_AI_PROVIDER_BASE_URL`.
- Use `POST /api/settings/test-ai-provider` to smoke test connectivity.
- Use Review page evaluation to verify the real user flow.
- Confirm evaluation events appear in card activity.
- Confirm review scheduling is unchanged by evaluation.

## 14. Code Pointers

Local backend:

- `apps/local-web/backend/app/api/routes/evaluations.py`
- `apps/local-web/backend/app/services/evaluation_service.py`
- `apps/local-web/backend/app/providers/ai/remote_http.py`
- `apps/local-web/backend/app/schemas/evaluation.py`
- `apps/local-web/backend/app/api/routes/settings.py`
- `apps/local-web/backend/app/services/activity_service.py`

Local frontend:

- `apps/local-web/frontend/src/features/review/review-session.tsx`
- `apps/local-web/frontend/src/api/activity.ts`
- `apps/local-web/frontend/src/features/settings/provider-form.tsx`

Tests:

- `apps/local-web/backend/tests/test_remote_ai_provider.py`
- `apps/local-web/backend/tests/test_activity_api.py`
