export type Citation = {
  id: string;
  artifact_id: string;
  quote: string;
  page?: number | null;
  paragraph?: number | null;
  start_seconds?: number | null;
  end_seconds?: number | null;
};

export type Review = {
  id: string;
  reviewer_id: string;
  decision: "CONFIRMED" | "CORRECTED" | "INSUFFICIENT_EVIDENCE" | "DISMISSED";
  corrected_label?: string | null;
  note?: string | null;
  created_at: string;
};

export type Indicator = {
  id: string;
  code: string;
  dimension: string;
  label: string;
  status: string;
  confidence: number;
  explanation: string;
  model_version: string;
  citations: Citation[];
  reviews: Review[];
};

export type Artifact = {
  id: string;
  evidence_type: string;
  filename: string;
  mime_type: string;
  page_count?: number | null;
  duration_seconds?: number | null;
  processing_status: string;
  extracted_summary?: string | null;
  technical_analysis?: {
    modality: string;
    status: string;
    analysis_method: string;
    metrics: Record<string, string | number | boolean | null>;
    error_message?: string | null;
    analyzed_at?: string | null;
  } | null;
};

export type CaseSummary = {
  id: string;
  teacher_code: string;
  teacher_display_name?: string | null;
  course_id: number;
  course_name: string;
  measurement: "LB" | "LF";
  status: string;
  region?: string | null;
  ugel?: string | null;
  education_level?: string | null;
  updated_at: string;
};

export type CaseDetail = CaseSummary & {
  executive_summary?: string | null;
  artifacts: Artifact[];
  indicators: Indicator[];
  identity?: {
    moodle_user_id: number;
    username?: string | null;
    full_name?: string | null;
    email?: string | null;
  } | null;
  moodle_submissions: Array<{
    id: string;
    course_id: number;
    cm_id: number;
    assignment_id: number;
    submission_id: number;
    activity_name: string;
    status: string;
    attempt_number: number;
    time_modified?: string | null;
    artifact_ids: string[];
  }>;
  ai_analysis?: {
    status: string;
    summary?: string | null;
    cluster_label?: string | null;
    risk_level: string;
    findings: Array<{ type: string; severity: string; title: string; detail: string; cm_id?: number | null; activity_name?: string | null; artifact_ids: string[]; confidence: number; score?: number | null; similarity_score?: number | null; validation_status?: string | null }>;
    model_version?: string | null;
    error_message?: string | null;
    analyzed_at?: string | null;
  } | null;
  rubric_assessments: Array<{
    id: string;
    cm_id: number;
    criterion_id: string;
    proposed_level: number;
    confidence: number;
    justification: string;
    evidence_artifact_ids: string[];
    validation_status: string;
    validated_level?: number | null;
    reviewer_note?: string | null;
    assessed_at: string;
    criterion_ref: { id: string; dimension: string; criterion: string; level_4: string; level_3: string; level_2: string; level_1: string; display_order: number };
  }>;
};

export type AnalyticsOverview = {
  teachers: number;
  cases: number;
  submissions: number;
  submitted: number;
  files: number;
  reviewed_signals: number;
  activities: Array<{ cm_id: number; activity_name: string; submissions: number; submitted: number; files: number }>;
  evidence_types: Array<{ evidence_type: string; count: number }>;
  analyzed_cases: number;
  pending_analysis: number;
  critical_findings: number;
  warning_findings: number;
  clusters: Array<{ label: string; count: number }>;
  finding_types: Array<{ type: string; count: number }>;
  teacher_analysis: Array<{ case_id: string; teacher: string; username?: string | null; status: string; risk_level: string; cluster?: string | null; findings: number; average_cmid_score?: number | null; coherence_score?: number | null; cmid_scores: Array<{ cm_id?: number | null; score?: number | null; similarity_score?: number | null; validation_status?: string | null }> }>;
  evidence_by_cmid: Array<{ cm_id: number; activity_name: string; evidence_type: string; count: number }>;
  video_comparison: Array<{ case_id: string; teacher: string; cm_id: number; activity_name: string; filename: string; duration_seconds?: number | null; width?: number | null; height?: number | null; fps?: number | null; has_audio?: boolean | null; sampled_frames?: number | null; status: string }>;
  document_metrics: Record<string, number | null>;
  document_comparison: Array<Record<string, string | number | boolean | null>>;
  video_metrics: Record<string, number | null>;
  similarity_edges: Array<{ source_case_id: string; target_case_id: string; source_artifact_id: string; target_artifact_id: string; source_teacher: string; target_teacher: string; source_filename: string; target_filename: string; source_cm_id?: number | null; target_cm_id?: number | null; same_cmid: boolean; score: number; literal?: number | null; method: string }>;
  similarity_meta?: { total_documents: number; documents_with_text: number; teachers_with_text: number; pending_documents: number; pairs_compared: number; pairs_with_similarity: number; exact_duplicate_pairs: number; max_score: number; mean_score: number; median_score: number; distribution: number[]; same_activity_only: boolean; edge_min_score: number; cluster_min_score: number };
  feedback_patterns: Array<{ type: string; count: number; average_confidence?: number | null }>;
  cluster_graph: { nodes: Array<{ id: string; label: string; cluster: number; ai_cluster?: string | null }>; edges: Array<{ source_case_id: string; target_case_id: string; score: number; method: string }>; cluster_count: number };
  rubric_analytics: { assessment_count: number; validated_count: number; dimensions: Array<{ dimension: string; average_level: number; level_4: number; level_3: number; level_2: number; level_1: number }>; by_teacher_cmid: Array<{ case_id: string; teacher: string; cm_id: number; average_level: number; pending_validation: number }> };
};
