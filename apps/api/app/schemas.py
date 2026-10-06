from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import CaseStatus, Measurement, ReviewDecision


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    artifact_id: str
    quote: str
    page: int | None = None
    paragraph: int | None = None
    start_seconds: int | None = None
    end_seconds: int | None = None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    reviewer_id: str
    decision: ReviewDecision
    corrected_label: str | None = None
    note: str | None = None
    created_at: datetime


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    dimension: str
    label: str
    status: str
    confidence: float
    explanation: str
    model_version: str
    citations: list[CitationOut] = []
    reviews: list[ReviewOut] = []


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    evidence_type: str
    filename: str
    mime_type: str
    source_url: str | None = None
    page_count: int | None = None
    duration_seconds: int | None = None
    processing_status: str
    extracted_summary: str | None = None
    technical_analysis: "ArtifactTechnicalAnalysisOut | None" = None


class ArtifactTechnicalAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    modality: str
    status: str
    analysis_method: str
    metrics: dict = Field(default_factory=dict)
    error_message: str | None = None
    analyzed_at: datetime | None = None


class MoodleIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    moodle_user_id: int
    username: str | None = None
    full_name: str | None = None
    email: str | None = None


class MoodleSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: int
    cm_id: int
    assignment_id: int
    submission_id: int
    activity_name: str
    status: str
    attempt_number: int
    time_modified: datetime | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class AIFindingOut(BaseModel):
    type: str
    severity: str
    title: str
    detail: str
    cm_id: int | None = None
    activity_name: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    score: float | None = None
    similarity_score: float | None = None
    validation_status: str | None = None


class CaseAIAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: str
    summary: str | None = None
    cluster_label: str | None = None
    risk_level: str
    findings: list[AIFindingOut] = Field(default_factory=list)
    model_version: str | None = None
    error_message: str | None = None
    analyzed_at: datetime | None = None


class RubricCriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dimension: str
    criterion: str
    level_4: str
    level_3: str
    level_2: str
    level_1: str
    display_order: int


class RubricAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    cm_id: int
    criterion_id: str
    proposed_level: int
    confidence: float
    justification: str
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    validation_status: str
    validated_level: int | None = None
    reviewer_note: str | None = None
    assessed_at: datetime
    criterion_ref: RubricCriterionOut


class CaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    teacher_code: str
    teacher_display_name: str | None = None
    course_id: int
    course_name: str
    measurement: Measurement
    status: CaseStatus
    region: str | None = None
    ugel: str | None = None
    education_level: str | None = None
    updated_at: datetime


class CaseDetail(CaseSummary):
    executive_summary: str | None = None
    artifacts: list[ArtifactOut] = []
    indicators: list[IndicatorOut] = []
    identity: MoodleIdentityOut | None = None
    moodle_submissions: list[MoodleSubmissionOut] = []
    ai_analysis: CaseAIAnalysisOut | None = None
    rubric_assessments: list[RubricAssessmentOut] = []


class AnalyticsActivityOut(BaseModel):
    cm_id: int
    activity_name: str
    submissions: int
    submitted: int
    files: int


class AnalyticsEvidenceOut(BaseModel):
    evidence_type: str
    count: int


class AnalyticsOverviewOut(BaseModel):
    teachers: int
    cases: int
    submissions: int
    submitted: int
    files: int
    reviewed_signals: int
    activities: list[AnalyticsActivityOut]
    evidence_types: list[AnalyticsEvidenceOut]
    analyzed_cases: int = 0
    pending_analysis: int = 0
    critical_findings: int = 0
    warning_findings: int = 0
    clusters: list[dict] = Field(default_factory=list)
    finding_types: list[dict] = Field(default_factory=list)
    teacher_analysis: list[dict] = Field(default_factory=list)
    evidence_by_cmid: list[dict] = Field(default_factory=list)
    video_comparison: list[dict] = Field(default_factory=list)
    document_metrics: dict = Field(default_factory=dict)
    document_comparison: list[dict] = Field(default_factory=list)
    video_metrics: dict = Field(default_factory=dict)
    similarity_edges: list[dict] = Field(default_factory=list)
    similarity_meta: dict = Field(default_factory=dict)
    feedback_patterns: list[dict] = Field(default_factory=list)
    cluster_graph: dict = Field(default_factory=dict)
    rubric_analytics: dict = Field(default_factory=dict)


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reviewer_id: str = Field(default="especialista-demo", max_length=120)
    corrected_label: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class MoodleEvent(BaseModel):
    event_id: str
    event_type: Literal["submission.created", "submission.updated", "submission.finalized"]
    occurred_at: datetime
    moodle_site_id: str
    course_id: int
    course_name: str = "Diplomado 2026"
    submission_id: int
    teacher_pseudonym_id: str
    measurement: Measurement
    manifest_version: int = 1
    manifest_url: str | None = None
    correlation_id: str
    region: str | None = None
    ugel: str | None = None
    education_level: str | None = None


class EventAccepted(BaseModel):
    event_id: str
    accepted: bool
    duplicate: bool
    case_id: str | None = None


class CaseQuery(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class GroundedAnswer(BaseModel):
    answer: str
    limitation: str
    citations: list[CitationOut]
    sources: list[dict] = Field(default_factory=list)


class AnalysisBatchRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list, max_length=500)
    force: bool = False


class SimilarityPrepareRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list, max_length=500)
    batch_size: int = Field(default=8, ge=1, le=20)
    retry_failed: bool = False


class SimilarityPrepareOut(BaseModel):
    total: int
    ready: int
    empty: int
    failed: int
    pending: int
    processed: int


class AnalysisQueuedOut(BaseModel):
    queued: int
    case_ids: list[str]




class MoodleScope(BaseModel):
    course_id: int | None = Field(default=None, gt=0)
    cm_id: int | None = Field(default=None, gt=0)
    cm_ids: list[int] = Field(default_factory=list, max_length=20)
    usernames: list[str] = Field(default_factory=list, max_length=100)


class MoodleActivityOut(BaseModel):
    assignment_id: int
    cm_id: int
    name: str
    submission_count: int = 0
    file_count: int = 0


class MoodlePreviewOut(BaseModel):
    site_name: str
    course_id: int
    course_name: str
    selected_cm_id: int | None = None
    selected_cm_ids: list[int] = Field(default_factory=list)
    requested_usernames: list[str] = Field(default_factory=list)
    matched_user_count: int = 0
    activities: list[MoodleActivityOut]
    submission_count: int
    file_count: int
    warnings: list[str] = Field(default_factory=list)


class MoodleImportRequest(MoodleScope):
    measurement: Measurement = Measurement.baseline


class MoodleImportOut(BaseModel):
    course_id: int
    selected_cm_id: int | None = None
    selected_cm_ids: list[int] = Field(default_factory=list)
    cases_created: int
    cases_updated: int
    artifacts_created: int
    case_ids: list[str]
    warnings: list[str] = Field(default_factory=list)


class ActivityCriterionUpsert(BaseModel):
    course_id: int = Field(gt=0)
    cm_id: int = Field(gt=0)
    activity_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=10, max_length=6000)
    expected_evidence: str = Field(min_length=3, max_length=4000)
    review_criteria: list[str] = Field(min_length=1, max_length=30)


class ActivityCriterionOut(ActivityCriterionUpsert):
    model_config = ConfigDict(from_attributes=True)
    id: str
    updated_at: datetime


class RubricValidationCreate(BaseModel):
    validated_level: int = Field(ge=1, le=4)
    reviewer_note: str | None = Field(default=None, max_length=3000)
