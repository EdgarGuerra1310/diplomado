import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_str() -> str:
    return str(uuid.uuid4())


class Measurement(str, enum.Enum):
    baseline = "LB"
    final = "LF"


class CaseStatus(str, enum.Enum):
    discovered = "DISCOVERED"
    processing = "PROCESSING"
    ready = "READY_FOR_REVIEW"
    in_review = "IN_REVIEW"
    reviewed = "REVIEWED"
    partial = "PARTIAL"
    failed = "FAILED_TECHNICAL"


class ReviewDecision(str, enum.Enum):
    confirmed = "CONFIRMED"
    corrected = "CORRECTED"
    insufficient = "INSUFFICIENT_EVIDENCE"
    dismissed = "DISMISSED"


class CaseFile(Base):
    __tablename__ = "case_files"
    __table_args__ = (UniqueConstraint("moodle_site_id", "submission_id", "manifest_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    teacher_code: Mapped[str] = mapped_column(String(80), index=True)
    teacher_display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    moodle_site_id: Mapped[str] = mapped_column(String(80), default="sifods")
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    course_name: Mapped[str] = mapped_column(String(240))
    submission_id: Mapped[int] = mapped_column(Integer, index=True)
    manifest_version: Mapped[int] = mapped_column(Integer, default=1)
    measurement: Mapped[Measurement] = mapped_column(Enum(Measurement))
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.discovered)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ugel: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    education_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    indicators: Mapped[list["IndicatorResult"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    identity: Mapped["MoodleIdentity"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    moodle_submissions: Mapped[list["MoodleSubmissionRecord"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    ai_analysis: Mapped["CaseAIAnalysis | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    rubric_assessments: Mapped[list["RubricAssessment"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class MoodleIdentity(Base):
    __tablename__ = "moodle_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_files.id", ondelete="CASCADE"), unique=True, index=True
    )
    moodle_user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    case: Mapped[CaseFile] = relationship(back_populates="identity")


class MoodleSubmissionRecord(Base):
    __tablename__ = "moodle_submission_records"
    __table_args__ = (
        UniqueConstraint("case_id", "assignment_id", "submission_id", "attempt_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_files.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    cm_id: Mapped[int] = mapped_column(Integer, index=True)
    assignment_id: Mapped[int] = mapped_column(Integer, index=True)
    submission_id: Mapped[int] = mapped_column(Integer, index=True)
    activity_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    attempt_number: Mapped[int] = mapped_column(Integer, default=0)
    time_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[CaseFile] = relationship(back_populates="moodle_submissions")


class ActivityReviewCriterion(Base):
    __tablename__ = "activity_review_criteria"
    __table_args__ = (UniqueConstraint("course_id", "cm_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    course_id: Mapped[int] = mapped_column(Integer, index=True)
    cm_id: Mapped[int] = mapped_column(Integer, index=True)
    activity_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    expected_evidence: Mapped[str] = mapped_column(Text)
    review_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(160), index=True)
    criterion: Mapped[str] = mapped_column(Text)
    level_4: Mapped[str] = mapped_column(Text)
    level_3: Mapped[str] = mapped_column(Text)
    level_2: Mapped[str] = mapped_column(Text)
    level_1: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(default=True)

    assessments: Mapped[list["RubricAssessment"]] = relationship(back_populates="criterion_ref")


class RubricAssessment(Base):
    __tablename__ = "rubric_assessments"
    __table_args__ = (UniqueConstraint("case_id", "cm_id", "criterion_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_files.id", ondelete="CASCADE"), index=True
    )
    cm_id: Mapped[int] = mapped_column(Integer, index=True)
    criterion_id: Mapped[str] = mapped_column(
        ForeignKey("rubric_criteria.id"), index=True
    )
    proposed_level: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    justification: Mapped[str] = mapped_column(Text)
    evidence_artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    validation_status: Mapped[str] = mapped_column(String(40), default="PENDING_HUMAN_REVIEW")
    validated_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[CaseFile] = relationship(back_populates="rubric_assessments")
    criterion_ref: Mapped[RubricCriterion] = relationship(back_populates="assessments")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_files.id", ondelete="CASCADE"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(80), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128))
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="PENDING")
    extracted_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[CaseFile] = relationship(back_populates="artifacts")
    citations: Mapped[list["Citation"]] = relationship(back_populates="artifact")
    technical_analysis: Mapped["ArtifactTechnicalAnalysis | None"] = relationship(
        back_populates="artifact", cascade="all, delete-orphan", uselist=False
    )


class ArtifactTechnicalAnalysis(Base):
    __tablename__ = "artifact_technical_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), unique=True, index=True
    )
    modality: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    analysis_method: Mapped[str] = mapped_column(String(120))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    artifact: Mapped[Artifact] = relationship(back_populates="technical_analysis")


class CaseAIAnalysis(Base):
    __tablename__ = "case_ai_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_files.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="PENDING", index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_label: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True)
    findings: Mapped[list[dict]] = mapped_column(JSON, default=list)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    case: Mapped[CaseFile] = relationship(back_populates="ai_analysis")


class IndicatorResult(Base):
    __tablename__ = "indicator_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("case_files.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80), index=True)
    dimension: Mapped[str] = mapped_column(String(120), index=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="POSSIBLE_EVIDENCE")
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(80), default="demo-rules-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[CaseFile] = relationship(back_populates="indicators")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="indicator", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["HumanReview"]] = relationship(
        back_populates="indicator", cascade="all, delete-orphan"
    )


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    indicator_id: Mapped[str] = mapped_column(
        ForeignKey("indicator_results.id", ondelete="CASCADE"), index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    quote: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    indicator: Mapped[IndicatorResult] = relationship(back_populates="citations")
    artifact: Mapped[Artifact] = relationship(back_populates="citations")


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    indicator_id: Mapped[str] = mapped_column(
        ForeignKey("indicator_results.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(120), default="especialista-demo")
    decision: Mapped[ReviewDecision] = mapped_column(Enum(ReviewDecision))
    corrected_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    indicator: Mapped[IndicatorResult] = relationship(back_populates="reviews")


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArtifactText(Base):
    __tablename__ = "artifact_texts"

    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
