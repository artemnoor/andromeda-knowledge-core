"""Pydantic request/response contracts for the versioned REST API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ApiErrorDetails(BaseModel):
    code: str = Field(examples=["RULE_CONFLICT"])
    message: str = Field(examples=["The rule conflicts with an active rule and needs review."])
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(examples=["7f9b2d14-7a3f-4a73-a0ad-2c8d6f6f0e31"])


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "RULE_CONFLICT",
                        "message": "The rule conflicts with an active rule and needs review.",
                        "details": {"review_id": "review-id"},
                        "trace_id": "7f9b2d14-7a3f-4a73-a0ad-2c8d6f6f0e31",
                    }
                }
            ]
        }
    )

    error: ApiErrorDetails


API_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ApiErrorResponse, "description": "Stable domain error envelope."},
    403: {"model": ApiErrorResponse, "description": "The caller does not have the required role."},
    404: {"model": ApiErrorResponse, "description": "The requested entity was not found."},
    409: {"model": ApiErrorResponse, "description": "Conflict, concurrent update or activation guard."},
    422: {"model": ApiErrorResponse, "description": "Request or domain validation failed."},
    500: {"model": ApiErrorResponse, "description": "Unexpected error with a trace ID."},
}


class ApiPage(BaseModel):
    items: list[Any]
    next_cursor: str | None = None


class OntologyCreate(StrictModel):
    version_code: str = Field(min_length=1, max_length=64, examples=["v1"])
    previous_version_id: str | None = None
    change_type: str = Field(default="BACKWARD_COMPATIBLE")
    migration_requirements: str | None = None


class ObjectTypeCreate(StrictModel):
    code: str = Field(min_length=1, max_length=128, examples=["University"])
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class PropertyDefinitionCreate(StrictModel):
    code: str = Field(min_length=1, max_length=128, examples=["admission.campaign_year"])
    value_type: str = Field(min_length=1, max_length=32, examples=["integer"])
    enum_values: list[str] | None = None
    allowed_object_types: list[str] = Field(default_factory=list)
    required: bool = False
    description: str = ""


class RelationTypeCreate(StrictModel):
    code: str = Field(min_length=1, max_length=128, examples=["OFFERS"])
    name: str
    allowed_source_types: list[str] = Field(default_factory=list)
    allowed_target_types: list[str] = Field(default_factory=list)
    cardinality: str = "MANY_TO_MANY"
    description: str = ""


class ObjectCreate(StrictModel):
    stable_key: str = Field(min_length=1, max_length=255, examples=["university:bmstu"])
    object_type_code: str = Field(min_length=1, max_length=128, examples=["University"])
    display_name: str = Field(min_length=1, max_length=255)
    properties: dict[str, Any] = Field(default_factory=dict)
    ontology_version_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class RelationCreate(StrictModel):
    subject_id: str
    relation_type_code: str
    object_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    ontology_version_id: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    provenance_id: str | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    confidence_status: str = "VERIFIED"


class FactCreate(StrictModel):
    subject_id: str
    property_code: str
    value: Any
    value_type: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    provenance_id: str | None = None
    source_id: str | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    confidence_status: str = "VERIFIED"
    verification_status: str = "VERIFIED"
    ontology_version_id: str | None = None


class SourceCreate(StrictModel):
    source_type: str = Field(examples=["PDF"])
    url: HttpUrl | None = None
    external_identifier: str | None = None
    publisher: str | None = None
    retrieved_at: datetime | None = None
    checksum: str | None = None
    content_metadata: dict[str, Any] = Field(default_factory=dict)
    trust_metadata: dict[str, Any] = Field(default_factory=dict)
    parser_version: str | None = None


class SourceDocumentCreate(StrictModel):
    source_id: str = Field(min_length=1)
    document_checksum: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=500)
    content_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime | None = None


class ObservationCreate(StrictModel):
    source_id: str
    source_document_id: str | None = None
    subject_candidate: dict[str, Any]
    property_candidate: str | None = None
    relation_candidate: dict[str, Any] | None = None
    value: Any = None
    value_type: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict, examples=[{"page": 14, "table": "quota"}])
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    confidence_status: str = "HIGH_CONFIDENCE"
    ontology_version_id: str | None = None
    idempotency_key: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class RuleTestCaseCreate(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    given_facts: list[dict[str, Any]] = Field(default_factory=list)
    given_relations: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    applicant: dict[str, Any] = Field(default_factory=dict)
    expected_effects: list[dict[str, Any]] = Field(default_factory=list)
    expected_explanation: str = ""


class RuleCreate(StrictModel):
    logical_key: str = Field(min_length=1, max_length=255, examples=["admission.additional_exam_bonus"])
    version: int | None = Field(default=None, ge=1)
    rule_type: str = "generic"
    scope: dict[str, Any] = Field(default_factory=dict)
    conditions: dict[str, Any]
    effects: list[dict[str, Any]]
    exceptions: list[dict[str, Any]] = Field(default_factory=list)
    priority: int = 0
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    ontology_version_id: str | None = None
    provenance_id: str | None = None
    replaces_rule_id: str | None = None
    relationships: list[dict[str, str]] = Field(default_factory=list, examples=[[{"relation_type": "OVERRIDES", "target_rule_id": "rule-id"}]])
    test_cases: list[RuleTestCaseCreate] = Field(default_factory=list)


class RuleTestRequest(StrictModel):
    test_cases: list[RuleTestCaseCreate] | None = None


class ReviewDecision(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)
    version: int | None = None
    modification: dict[str, Any] | None = None


class ApplicantContext(StrictModel):
    scores: dict[str, Decimal | int | float] = Field(default_factory=dict)
    additional_exams: list[dict[str, Any]] = Field(default_factory=list)
    achievements: list[dict[str, Any]] = Field(default_factory=list)
    olympiads: list[dict[str, Any]] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    additional: dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(StrictModel):
    applicant: ApplicantContext = Field(default_factory=ApplicantContext)
    context: dict[str, Any] = Field(default_factory=dict, examples=[{"base_score": 275, "campaign_year": 2027}])
    derived_type: str = "admission_evaluation"
    persist: bool = True


class Overlay(StrictModel):
    property: str = Field(min_length=1, examples=["scores.physics"])
    value: Any


class SimulateRequest(StrictModel):
    base_context: EvaluateRequest
    overrides: list[Overlay] = Field(default_factory=list)


class SemanticEvaluateResponse(BaseModel):
    result_id: str | None = None
    derived_type: str
    value: dict[str, Any]
    matched_rules: list[dict[str, Any]]
    explanation_summary: str
    trace: dict[str, Any]
    rule_versions: list[dict[str, Any]]
    duration_ms: float
    instrumentation: dict[str, Any]
    computed_at: datetime | None = None
    engine_version: str | None = None
    ontology_version_id: str | None = None
    cached: bool | None = None
    persisted: bool = False


class SemanticSimulationResponse(BaseModel):
    before: SemanticEvaluateResponse
    after: SemanticEvaluateResponse
    delta: dict[str, Any]
    overrides: list[Overlay]
    persisted_changes: list[Any]


class ExplainResponse(BaseModel):
    result: dict[str, Any]
    explanation: str
    nodes: list[dict[str, Any]]
    metadata: dict[str, Any]


class PaginationQuery(StrictModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
