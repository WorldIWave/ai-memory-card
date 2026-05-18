// Input: 无（纯类型声明文件）  |  Output: 前后端共享的 TS 类型与接口
// Role: API 类型中枢，定义 Deck、Card、System、Evaluation 等所有响应结构
// Note: DeckVisibility / CardStatus 使用 `string & {}` 扩展以兼容未来新状态值
// Usage: import type { DeckRead, CardRead } from "@/api/types";
export type ApiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiErrorShape {
  message: string;
  status?: number;
}

export type DeckVisibility = "normal" | "archived" | (string & {});

export interface DeckRead {
  id: number;
  name: string;
  description: string;
  default_scheduler_type: string;
  visibility: DeckVisibility;
  folder_id: number | null;
  created_at: string;
}

export interface DeckUpdateInput {
  name: string;
  description: string;
  folder_id: number;
}

export interface FolderRead {
  id: number;
  name: string;
}

export interface FolderUpdateInput {
  name: string;
}

export type CardStatus = "active" | "archived" | (string & {});

export type ReviewGrade = "again" | "hard" | "good" | "easy";
export type ReviewSessionScope = "deck" | "all";
export type ReviewSessionAction = "remove" | "reinsert" | "repeat_now";
export type StatsAnalyticsRangeDays = 7 | 30;

export interface ReviewSessionCounts {
  new: number;
  learning: number;
  review: number;
  relearning: number;
  total: number;
}

export interface SessionScheduleResult {
  card_id: number;
  scheduler_type: string;
  next_due_at: string;
  interval_days: number;
  reason: string;
  session_action: ReviewSessionAction;
  reinsert_after: number | null;
  learning_state: string;
  learning_step: number;
  session_repeats_today: number;
  hard_attempts_today: number;
  repetition_delta: number;
  lapses_delta: number;
  state_patch: Record<string, unknown>;
  explainability: Record<string, string | number>;
}

export interface ReviewSessionRead {
  session_id: string;
  scope: ReviewSessionScope;
  deck_id: number | null;
  queue: CardRead[];
  counts: ReviewSessionCounts;
  can_undo: boolean;
}

export interface ReviewSessionSubmitInput {
  card_id: number;
  grade: ReviewGrade;
  review_mode: string;
  trigger_type: "scheduled";
}

export interface ReviewSessionSubmitResponse extends ReviewSessionRead {
  decision: SessionScheduleResult;
}

export interface ReviewSessionUndoResponse extends ReviewSessionRead {
  restored_card_id: number | null;
}

export interface CardRead {
  id: number;
  deck_id: number;
  knowledge_unit_ref_id?: number | null;
  card_type: string;
  front: string;
  back: string;
  render_format: string;
  tags: string[];
  status: CardStatus;
  created_at: string;
  updated_at?: string;
  content_version?: number;
}

export interface CardUpdateInput {
  deck_id: number;
  card_type: string;
  front: string;
  back: string;
  render_format: string;
  tags: string[];
}

export type CardActivityEventType = "review" | "evaluation" | "report_error" | "note" | (string & {});

export interface CardActivityItem {
  id: string;
  event_type: CardActivityEventType;
  created_at: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface ReviewHistoryItem {
  id: number;
  card_id: number;
  deck_id: number | null;
  card_front: string;
  deck_name: string | null;
  grade: string;
  interval_days: number | null;
  reviewed_at: string;
  session_id: string | null;
}

export interface ReportCardInput {
  reason: string;
  note: string;
}

export interface CardNoteCreateInput {
  note: string;
  source?: string | null;
}

export interface EvaluationSubmitInput {
  card_id?: number | null;
  target_unit: Record<string, unknown>;
  learner_explanation: string;
  reference_material?: string | null;
  rubric_version?: string;
  persist?: boolean;
}

export interface CardEvaluationSubmitInput extends EvaluationSubmitInput {
  card_id: number;
}

export interface EvaluationRecordInput {
  card_id: number;
  learner_explanation: string;
  result: EvaluationRead;
}

export interface ScheduleDecision {
  card_id: number;
  scheduler_type: string;
  next_due_at: string;
  interval_days: number;
  reason: string;
}

export interface EvaluationRead {
  mastery_score: number;
  accuracy_score: number;
  concept_score: number;
  mechanism_score: number;
  boundary_score: number;
  misconception_score: number;
  misconception_detected: boolean;
  confidence_score: number;
  uncertain: boolean;
  feedback: string;
  weak_points: string[];
  reinforcement_advice: string[];
  rubric_version: string;
  provider_meta: Record<string, unknown>;
  trace_id?: string | null;
}

export interface StatsSummaryRead {
  total_cards: number;
  today_reviewed: number;
  daily_new_avg: number;
  daily_review_avg: number;
}

export interface StatsTrendPointRead {
  date: string;
  review_count: number;
}

export interface StatsTrendRead {
  range_days: StatsAnalyticsRangeDays;
  points: StatsTrendPointRead[];
}

export interface GradeDistributionItemRead {
  grade: ReviewGrade;
  count: number;
  ratio: number;
}

export interface GradeDistributionRead {
  total_reviews: number;
  items: GradeDistributionItemRead[];
}

export interface DeckActivityItemRead {
  deck_id: number;
  deck_name: string;
  review_count: number;
  unique_cards: number;
}

export interface DeckActivityRead {
  range_days: StatsAnalyticsRangeDays;
  items: DeckActivityItemRead[];
}

export interface StatsAnalyticsRead {
  summary: StatsSummaryRead;
  trend: StatsTrendRead;
  grade_distribution: GradeDistributionRead;
  deck_activity: DeckActivityRead;
}

export interface SettingsRead {
  app_name: string;
  ai_provider: string;
  ai_provider_base_url: string | null;
}

export type PluginState =
  | "not_installed"
  | "installed_disabled"
  | "enabled_not_configured"
  | "enabled_starting"
  | "enabled_unhealthy"
  | "ready"
  | "busy";

export interface PluginStatusRead {
  plugin_id: string;
  plugin_name: string;
  plugin_version: string;
  protocol_version: string;
  enabled: boolean;
  state: PluginState;
  health: Record<string, unknown>;
  capabilities: Record<string, unknown>[];
  configuration: {
    provider_profile?: string;
    base_url?: string | null;
    api_key_configured?: boolean;
    model?: string | null;
  };
}

export interface PluginConfigUpdateInput {
  enabled: boolean;
  provider_profile: string;
  base_url: string | null;
  api_key?: string | null;
  model: string | null;
}

export interface PluginConfigRead {
  enabled: boolean;
  provider_profile: string;
  base_url: string | null;
  model: string | null;
}

export type SchedulerMode = "traditional" | "ai_rl";

export interface StudySettingsRead {
  daily_new_limit: number;
  daily_review_limit: number;
  scheduler_mode: SchedulerMode;
  updated_at: string;
}

export interface StudySettingsUpdateInput {
  daily_new_limit: number;
  daily_review_limit: number;
  scheduler_mode: SchedulerMode;
}

export interface ImportCardsResponse {
  deck: DeckRead;
  cards: CardRead[];
  imported_count: number;
}

export interface RAGImportDocumentInput {
  filename: string;
  content_type: string;
  text: string;
}

export interface RAGImportCardsInput {
  deck_id?: number;
  deck_name?: string;
  documents: RAGImportDocumentInput[];
  topics?: string[];
  generation_prefs?: {
    backend: "extractive" | "llm";
    card_types: string[];
    max_cards_per_unit: number;
    language: string;
    max_candidates?: number | null;
    max_final_questions?: number | null;
    candidate_unit_batch_size?: number | null;
    candidate_batch_max_chars?: number | null;
    candidate_context_max_chars?: number | null;
    judge_max_pairs_per_call?: number | null;
    adaptive_batching_enabled?: boolean;
    model_context_tokens?: number | null;
    reserved_output_tokens?: number | null;
    target_chunk_tokens?: number | null;
    extractor_batch_mode?: "block" | "section" | "token-window";
    extractor_max_blocks?: number | null;
    extractor_max_chars?: number | null;
    extractor_max_tokens?: number | null;
    extractor_batch_max_chars?: number | null;
    extractor_preselect_max_blocks?: number | null;
    extractor_preselect_min_score?: number | null;
    disable_extractor_preselect?: boolean;
    disable_extractor_adaptive_max_blocks?: boolean;
    extractor_adaptive_min_blocks?: number | null;
    extractor_adaptive_max_blocks_limit?: number | null;
    prefer_aggregate_units?: boolean;
  };
}

export interface RAGImportCardsResponse extends ImportCardsResponse {
  knowledge_units: Record<string, unknown>[];
  warnings: string[];
  provider_meta: Record<string, unknown>;
}

export interface KnowledgeUnitRead {
  id: number;
  deck_id: number;
  provider_unit_id: string;
  topic: string;
  summary: string;
  source_document?: string | null;
  source_span?: Record<string, unknown> | null;
  raw_payload: Record<string, unknown>;
  created_at: string;
}

export interface ExportCardsResponse {
  format: "json" | "csv" | "markdown";
  payload:
    | {
        decks: DeckRead[];
        cards: CardRead[];
      }
    | string;
}

export interface SystemBackupRead {
  filename: string;
  path: string;
  size_bytes: number;
  modified_at: string;
}

export interface SystemRestoreResponse {
  restored_from: string;
  database_path: string;
}

export interface SystemRuntimeRead {
  app_name: string;
  app_version: string;
  backend_version: string;
  backend_root: string;
  app_data_dir: string;
  database_path: string;
  backup_dir: string;
  log_dir: string;
  cache_dir: string;
  runtime_mode: string;
  release_channel_url?: string | null;
  python_executable?: string | null;
  python_version?: string | null;
  backend_port: number | null;
}

export interface DataDirectoryStateRead {
  runtime_mode: string;
  current_app_data_root: string;
  default_app_data_root: string;
  custom_app_data_root: string | null;
  migration_allowed: boolean;
  pending_target_app_data_root: string | null;
  desktop_bridge_available: boolean;
}

export interface SystemLogFileRead {
  name: string;
  path: string;
  size_bytes: number;
}

export interface SystemDiagnosticsRead extends SystemRuntimeRead {
  database_exists: boolean;
  database_size_bytes: number;
  backup_count: number;
  backups: SystemBackupRead[];
  log_files: SystemLogFileRead[];
}

export interface CardAssetDraftResponse {
  draft_id: string;
}

export interface CardAssetUploadResponse {
  asset_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  url: string;
  markdown: string;
}
