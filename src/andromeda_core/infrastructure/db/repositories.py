"""SQLAlchemy repository adapter for the Knowledge Core use cases."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import and_, desc, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.domain.common import DerivedStatus, utc_now
from andromeda_core.domain.errors import ConflictError, NotFoundError
from andromeda_core.infrastructure.db.models import (
    AuditEventModel,
    Base,
    ChangeEventModel,
    DependencyModel,
    DerivedValueModel,
    FactModel,
    KnowledgeObjectModel,
    ObjectTypeModel,
    ObservationModel,
    OntologyChangeProposalModel,
    OntologyVersionModel,
    PropertyDefinitionModel,
    ProvenanceRecordModel,
    RelationModel,
    RelationTypeModel,
    ReviewItemModel,
    RuleModel,
    RuleRelationModel,
    RuleTestCaseModel,
    SourceDocumentModel,
    SourceModel,
)

ModelT = TypeVar("ModelT", bound=Base)


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default, ensure_ascii=False))


def _json_default(value: Any) -> str | float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def serialize_model(model: Base) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if isinstance(value, Decimal):
            value = float(value)
        result[column.name] = value
    return result


class CoreRepository:
    """Deep persistence adapter behind a small application-facing seam."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def flush(self) -> None:
        await self.session.flush()

    async def _get(self, model: type[ModelT], entity_id: str, entity_name: str) -> ModelT:
        entity = await self.session.get(model, entity_id)
        if entity is None:
            raise NotFoundError(entity_name, entity_id)
        return entity

    async def get_ontology(self, ontology_id: str) -> dict[str, Any]:
        ontology = await self._get(OntologyVersionModel, ontology_id, "ontology_version")
        return serialize_model(ontology)

    async def get_active_ontology(self) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(OntologyVersionModel).where(OntologyVersionModel.status == "ACTIVE").order_by(desc(OntologyVersionModel.created_at)).limit(1)
        )
        ontology = result.scalar_one_or_none()
        return serialize_model(ontology) if ontology else None

    async def list_ontologies(self) -> list[dict[str, Any]]:
        result = await self.session.execute(select(OntologyVersionModel).order_by(desc(OntologyVersionModel.created_at)))
        return [serialize_model(item) for item in result.scalars()]

    async def create_ontology(self, data: dict[str, Any]) -> dict[str, Any]:
        model = OntologyVersionModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def update_ontology(self, ontology_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        ontology = await self._get(OntologyVersionModel, ontology_id, "ontology_version")
        current_version = ontology.row_version
        if expected_version is not None and current_version != expected_version:
            raise ConflictError("CONCURRENT_MODIFICATION", "Ontology version was modified by another process.")
        result = await self.session.execute(
            update(OntologyVersionModel)
            .where(OntologyVersionModel.id == ontology_id, OntologyVersionModel.row_version == current_version)
            .values(**data, row_version=current_version + 1)
        )
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_MODIFICATION", "Ontology version was modified by another process.")
        await self.session.refresh(ontology)
        return serialize_model(ontology)

    async def ontology_definitions(self, ontology_id: str) -> dict[str, list[dict[str, Any]]]:
        object_types = await self.session.execute(select(ObjectTypeModel).where(ObjectTypeModel.ontology_version_id == ontology_id))
        properties = await self.session.execute(select(PropertyDefinitionModel).where(PropertyDefinitionModel.ontology_version_id == ontology_id))
        relations = await self.session.execute(select(RelationTypeModel).where(RelationTypeModel.ontology_version_id == ontology_id))
        return {
            "object_types": [serialize_model(item) for item in object_types.scalars()],
            "properties": [serialize_model(item) for item in properties.scalars()],
            "relation_types": [serialize_model(item) for item in relations.scalars()],
        }

    async def create_definition(self, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        models: dict[str, type[Base]] = {
            "object_type": ObjectTypeModel,
            "property": PropertyDefinitionModel,
            "relation_type": RelationTypeModel,
        }
        model = models.get(kind)
        if model is None:
            raise ConflictError("INVALID_DEFINITION_KIND", f"Unknown ontology definition kind '{kind}'.")
        instance = model(**data)
        self.session.add(instance)
        await self.flush()
        return serialize_model(instance)

    async def find_object(self, object_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(KnowledgeObjectModel, object_id, "knowledge_object"))

    async def find_object_by_key(self, stable_key: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(KnowledgeObjectModel).where(KnowledgeObjectModel.stable_key == stable_key))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def list_objects(self, object_type_code: str | None = None) -> list[dict[str, Any]]:
        query = select(KnowledgeObjectModel).order_by(KnowledgeObjectModel.display_name)
        if object_type_code:
            query = query.where(KnowledgeObjectModel.object_type_code == object_type_code)
        result = await self.session.execute(query)
        return [serialize_model(item) for item in result.scalars()]

    async def upsert_object(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.find_object_by_key(data["stable_key"])
        if existing:
            return existing
        model = KnowledgeObjectModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def find_source(self, source_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(SourceModel, source_id, "source"))

    async def find_source_by_identity(self, source_type: str, external_identifier: str | None, checksum: str | None) -> dict[str, Any] | None:
        conditions = [SourceModel.source_type == source_type]
        if external_identifier:
            conditions.append(SourceModel.external_identifier == external_identifier)
        elif checksum:
            conditions.append(SourceModel.checksum == checksum)
        else:
            return None
        result = await self.session.execute(select(SourceModel).where(and_(*conditions)).limit(1))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def upsert_source(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.find_source_by_identity(data["source_type"], data.get("external_identifier"), data.get("checksum"))
        if existing:
            return existing
        model = SourceModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def list_sources(self) -> list[dict[str, Any]]:
        result = await self.session.execute(select(SourceModel).order_by(desc(SourceModel.created_at)))
        return [serialize_model(item) for item in result.scalars()]

    async def find_source_document(self, source_id: str, document_checksum: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(SourceDocumentModel).where(
                SourceDocumentModel.source_id == source_id,
                SourceDocumentModel.document_checksum == document_checksum,
            )
        )
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def create_source_document(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.find_source_document(data["source_id"], data["document_checksum"])
        if existing:
            return existing
        model = SourceDocumentModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def find_observation_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(ObservationModel).where(ObservationModel.idempotency_key == idempotency_key))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def get_observation(self, observation_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(ObservationModel, observation_id, "observation"))

    async def create_observation(self, data: dict[str, Any]) -> dict[str, Any]:
        model = ObservationModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def update_observation(self, observation_id: str, data: dict[str, Any]) -> dict[str, Any]:
        model = await self._get(ObservationModel, observation_id, "observation")
        for key, value in data.items():
            setattr(model, key, value)
        model.updated_at = utc_now()
        model.row_version += 1
        await self.flush()
        return serialize_model(model)

    async def create_provenance(self, data: dict[str, Any]) -> dict[str, Any]:
        model = ProvenanceRecordModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def get_provenance(self, provenance_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(ProvenanceRecordModel, provenance_id, "provenance_record"))

    async def get_fact(self, fact_id: str) -> dict[str, Any]:
        model = await self._get(FactModel, fact_id, "fact")
        return self._fact_dict(model)

    async def find_fact_by_identity(self, identity_key: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(FactModel).where(FactModel.identity_key == identity_key))
        model = result.scalar_one_or_none()
        return self._fact_dict(model) if model else None

    async def create_fact(self, data: dict[str, Any]) -> dict[str, Any]:
        model = FactModel(**_fact_columns(data))
        self.session.add(model)
        await self.flush()
        return self._fact_dict(model)

    async def close_fact_transaction(self, fact_id: str, transaction_to: datetime) -> None:
        """Close the current transaction-time version before inserting a correction."""

        result = await self.session.execute(
            update(FactModel)
            .where(FactModel.id == fact_id, FactModel.transaction_to.is_(None))
            .values(transaction_to=transaction_to)
        )
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_MODIFICATION", "Fact was changed by another process.")

    async def list_facts(
        self,
        *,
        subject_id: str | None = None,
        property_code: str | None = None,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        query = select(FactModel)
        conditions = []
        if subject_id:
            conditions.append(FactModel.subject_id == subject_id)
        if property_code:
            conditions.append(FactModel.property_code == property_code)
        if valid_at:
            conditions.extend([or_(FactModel.valid_from.is_(None), FactModel.valid_from <= valid_at), or_(FactModel.valid_to.is_(None), valid_at < FactModel.valid_to)])
        if known_at:
            conditions.extend([FactModel.transaction_from <= known_at, or_(FactModel.transaction_to.is_(None), known_at < FactModel.transaction_to)])
        else:
            conditions.append(FactModel.transaction_to.is_(None))
        if conditions:
            query = query.where(and_(*conditions))
        result = await self.session.execute(query.order_by(FactModel.property_code, FactModel.id))
        return [self._fact_dict(item) for item in result.scalars()]

    async def create_relation(self, data: dict[str, Any]) -> dict[str, Any]:
        model = RelationModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def get_relation(self, relation_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(RelationModel, relation_id, "relation"))

    async def find_relation_by_identity(self, identity_key: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(RelationModel).where(RelationModel.identity_key == identity_key))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def list_relations(
        self,
        subject_id: str | None = None,
        relation_type_code: str | None = None,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        query = select(RelationModel)
        conditions = []
        if subject_id:
            conditions.append(RelationModel.subject_id == subject_id)
        if relation_type_code:
            conditions.append(RelationModel.relation_type_code == relation_type_code)
        if valid_at:
            conditions.extend([or_(RelationModel.valid_from.is_(None), RelationModel.valid_from <= valid_at), or_(RelationModel.valid_to.is_(None), valid_at < RelationModel.valid_to)])
        if known_at:
            conditions.extend([RelationModel.transaction_from <= known_at, or_(RelationModel.transaction_to.is_(None), known_at < RelationModel.transaction_to)])
        else:
            conditions.append(RelationModel.transaction_to.is_(None))
        if conditions:
            query = query.where(and_(*conditions))
        result = await self.session.execute(query.order_by(RelationModel.id))
        return [serialize_model(item) for item in result.scalars()]

    async def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        model = RuleModel(**data)
        self.session.add(model)
        try:
            await self.flush()
        except IntegrityError as exc:
            await self.rollback()
            raise ConflictError("RULE_CREATE_CONFLICT", "Rule version or idempotency key already exists.") from exc
        return serialize_model(model)

    async def find_rule_by_idempotency(self, idempotency_key: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(RuleModel).where(RuleModel.idempotency_key == idempotency_key).limit(1))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def get_rule(self, rule_id: str) -> dict[str, Any]:
        model = await self._get(RuleModel, rule_id, "rule")
        result = serialize_model(model)
        result["test_cases"] = await self.list_rule_tests(rule_id)
        result["relationships"] = await self.list_rule_relations(rule_id)
        return result

    async def list_rules(self, status: str | None = None) -> list[dict[str, Any]]:
        query = select(RuleModel).order_by(RuleModel.logical_key, RuleModel.version)
        if status:
            query = query.where(RuleModel.status == status)
        result = await self.session.execute(query)
        return [serialize_model(item) for item in result.scalars()]

    async def active_rules(self, *, valid_at: datetime | None = None, known_at: datetime | None = None) -> list[dict[str, Any]]:
        conditions = []
        if known_at:
            # A superseded row remains active for the transaction-time interval
            # before the replacement was accepted. This preserves historical
            # rule snapshots without duplicating logical rule versions.
            conditions.append(
                or_(
                    RuleModel.status == "ACTIVE",
                    and_(RuleModel.status == "SUPERSEDED", RuleModel.transaction_to.is_not(None)),
                )
            )
        else:
            conditions.append(RuleModel.status == "ACTIVE")
        if valid_at:
            conditions.extend([or_(RuleModel.valid_from.is_(None), RuleModel.valid_from <= valid_at), or_(RuleModel.valid_to.is_(None), valid_at < RuleModel.valid_to)])
        if known_at:
            conditions.extend([RuleModel.transaction_from <= known_at, or_(RuleModel.transaction_to.is_(None), known_at < RuleModel.transaction_to)])
        else:
            conditions.append(RuleModel.transaction_to.is_(None))
        result = await self.session.execute(select(RuleModel).where(and_(*conditions)).order_by(desc(RuleModel.priority), RuleModel.logical_key, RuleModel.version))
        rules = [serialize_model(item) for item in result.scalars()]
        for rule in rules:
            rule["test_cases"] = await self.list_rule_tests(rule["id"])
        return rules

    async def update_rule(self, rule_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        model = await self._get(RuleModel, rule_id, "rule")
        current_version = model.row_version
        if expected_version is not None and current_version != expected_version:
            raise ConflictError("CONCURRENT_MODIFICATION", "Rule was modified by another process.")
        result = await self.session.execute(
            update(RuleModel)
            .where(RuleModel.id == rule_id, RuleModel.row_version == current_version)
            .values(**data, row_version=current_version + 1, updated_at=utc_now())
        )
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_MODIFICATION", "Rule was modified by another process.")
        await self.session.refresh(model)
        return serialize_model(model)

    async def find_rule_version(self, logical_key: str, version: int) -> dict[str, Any] | None:
        result = await self.session.execute(select(RuleModel).where(RuleModel.logical_key == logical_key, RuleModel.version == version))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def create_rule_test(self, data: dict[str, Any]) -> dict[str, Any]:
        model = RuleTestCaseModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def create_rule_relation(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = await self.session.execute(
            select(RuleRelationModel).where(
                RuleRelationModel.source_rule_id == data["source_rule_id"],
                RuleRelationModel.relation_type == data["relation_type"],
                RuleRelationModel.target_rule_id == data["target_rule_id"],
            )
        )
        model = existing.scalar_one_or_none()
        if model:
            return serialize_model(model)
        model = RuleRelationModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def list_rule_relations(self, rule_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(RuleRelationModel).where(
                or_(RuleRelationModel.source_rule_id == rule_id, RuleRelationModel.target_rule_id == rule_id)
            ).order_by(RuleRelationModel.relation_type, RuleRelationModel.source_rule_id, RuleRelationModel.target_rule_id)
        )
        return [serialize_model(item) for item in result.scalars()]

    async def list_rule_tests(self, rule_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(select(RuleTestCaseModel).where(RuleTestCaseModel.rule_id == rule_id).order_by(RuleTestCaseModel.name))
        return [serialize_model(item) for item in result.scalars()]

    async def update_rule_test(self, test_id: str, data: dict[str, Any]) -> dict[str, Any]:
        model = await self._get(RuleTestCaseModel, test_id, "rule_test_case")
        for key, value in data.items():
            setattr(model, key, value)
        await self.flush()
        return serialize_model(model)

    async def get_derived(self, derived_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(DerivedValueModel, derived_id, "derived_value"))

    async def find_derived_by_key(self, result_key: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(DerivedValueModel).where(DerivedValueModel.result_key == result_key))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def create_derived(self, data: dict[str, Any]) -> dict[str, Any]:
        model = DerivedValueModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def update_derived(self, derived_id: str, data: dict[str, Any]) -> dict[str, Any]:
        model = await self._get(DerivedValueModel, derived_id, "derived_value")
        current_version = model.row_version
        result = await self.session.execute(
            update(DerivedValueModel)
            .where(DerivedValueModel.id == derived_id, DerivedValueModel.row_version == current_version)
            .values(**data, updated_at=utc_now(), row_version=current_version + 1)
        )
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_MODIFICATION", "Derived value was modified by another process.")
        await self.session.refresh(model)
        return serialize_model(model)

    async def add_dependency(self, data: dict[str, Any]) -> dict[str, Any]:
        model = DependencyModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def dependencies_from(self, source_kind: str, source_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(select(DependencyModel).where(DependencyModel.source_kind == source_kind, DependencyModel.source_id == source_id))
        return [serialize_model(item) for item in result.scalars()]

    async def dependencies_to(self, target_kind: str, target_id: str) -> list[dict[str, Any]]:
        result = await self.session.execute(select(DependencyModel).where(DependencyModel.target_kind == target_kind, DependencyModel.target_id == target_id))
        return [serialize_model(item) for item in result.scalars()]

    async def invalidate_derived(self, derived_ids: list[str], reason: str) -> int:
        if not derived_ids:
            return 0
        result = await self.session.execute(
            update(DerivedValueModel)
            .where(DerivedValueModel.id.in_(derived_ids), DerivedValueModel.status == DerivedStatus.VALID.value)
            .values(status=DerivedStatus.INVALIDATED.value, invalidation_reason=reason, updated_at=utc_now(), row_version=DerivedValueModel.row_version + 1)
        )
        return int(result.rowcount or 0)

    async def create_review(self, data: dict[str, Any]) -> dict[str, Any]:
        model = ReviewItemModel(
            **{
                **data,
                "evidence_json": json_safe(data.get("evidence_json", {})),
                "proposed_change_json": json_safe(data.get("proposed_change_json", {})),
                "decision_json": json_safe(data.get("decision_json", {})),
            }
        )
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def get_review(self, review_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(ReviewItemModel, review_id, "review_item"))

    async def list_reviews(self, status: str | None = None) -> list[dict[str, Any]]:
        query = select(ReviewItemModel).order_by(desc(ReviewItemModel.created_at))
        if status:
            query = query.where(ReviewItemModel.status == status)
        result = await self.session.execute(query)
        return [serialize_model(item) for item in result.scalars()]

    async def find_open_review(self, entity_type: str, entity_id: str, reason: str) -> dict[str, Any] | None:
        result = await self.session.execute(select(ReviewItemModel).where(ReviewItemModel.entity_type == entity_type, ReviewItemModel.entity_id == entity_id, ReviewItemModel.reason == reason, ReviewItemModel.status == "NEEDS_REVIEW").limit(1))
        model = result.scalar_one_or_none()
        return serialize_model(model) if model else None

    async def update_review(self, review_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        model = await self._get(ReviewItemModel, review_id, "review_item")
        current_version = model.row_version
        if expected_version is not None and current_version != expected_version:
            raise ConflictError("CONCURRENT_MODIFICATION", "Review item was modified by another process.")
        result = await self.session.execute(
            update(ReviewItemModel)
            .where(ReviewItemModel.id == review_id, ReviewItemModel.row_version == current_version)
            .values(**data, row_version=current_version + 1, updated_at=utc_now())
        )
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_MODIFICATION", "Review item was modified by another process.")
        await self.session.refresh(model)
        return serialize_model(model)

    async def create_proposal(self, data: dict[str, Any]) -> dict[str, Any]:
        model = OntologyChangeProposalModel(**data)
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        query = select(OntologyChangeProposalModel).order_by(desc(OntologyChangeProposalModel.created_at))
        if status:
            query = query.where(OntologyChangeProposalModel.status == status)
        result = await self.session.execute(query)
        return [serialize_model(item) for item in result.scalars()]

    async def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        return serialize_model(await self._get(OntologyChangeProposalModel, proposal_id, "ontology_change_proposal"))

    async def update_proposal(self, proposal_id: str, data: dict[str, Any], expected_version: int | None = None) -> dict[str, Any]:
        model = await self._get(OntologyChangeProposalModel, proposal_id, "ontology_change_proposal")
        current_version = model.row_version
        if expected_version is not None and current_version != expected_version:
            raise ConflictError("CONCURRENT_MODIFICATION", "Ontology proposal was modified by another process.")
        result = await self.session.execute(
            update(OntologyChangeProposalModel)
            .where(OntologyChangeProposalModel.id == proposal_id, OntologyChangeProposalModel.row_version == current_version)
            .values(**data, row_version=current_version + 1, updated_at=utc_now())
        )
        if result.rowcount != 1:
            raise ConflictError("CONCURRENT_MODIFICATION", "Ontology proposal was modified by another process.")
        await self.session.refresh(model)
        return serialize_model(model)

    async def create_audit(self, data: dict[str, Any]) -> dict[str, Any]:
        model = AuditEventModel(
            **{
                **data,
                "before_json": json_safe(data.get("before_json")),
                "after_json": json_safe(data.get("after_json")),
            }
        )
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def list_audit(self, entity_type: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
        query = select(AuditEventModel).order_by(desc(AuditEventModel.created_at))
        if entity_type:
            query = query.where(AuditEventModel.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditEventModel.entity_id == entity_id)
        result = await self.session.execute(query)
        return [serialize_model(item) for item in result.scalars()]

    async def create_change(self, data: dict[str, Any]) -> dict[str, Any]:
        model = ChangeEventModel(
            **{
                **data,
                "before_json": json_safe(data.get("before_json")),
                "after_json": json_safe(data.get("after_json")),
            }
        )
        self.session.add(model)
        await self.flush()
        return serialize_model(model)

    async def list_changes(self, classification: str | None = None) -> list[dict[str, Any]]:
        query = select(ChangeEventModel).order_by(desc(ChangeEventModel.created_at))
        if classification:
            query = query.where(ChangeEventModel.classification == classification)
        result = await self.session.execute(query)
        return [serialize_model(item) for item in result.scalars()]

    async def _provenance_chain(self, provenance_id: str) -> dict[str, Any]:
        provenance = await self._get(ProvenanceRecordModel, provenance_id, "provenance_record")
        source = await self._get(SourceModel, provenance.source_id, "source")
        observation = None
        if provenance.observation_id:
            observation = await self._get(ObservationModel, provenance.observation_id, "observation")
        return {"provenance": serialize_model(provenance), "observation": serialize_model(observation) if observation else None, "source": serialize_model(source)}

    async def explain_provenance(self, provenance_id: str) -> dict[str, Any]:
        """Return the source/evidence chain for any provenance-bearing entity."""

        return await self._provenance_chain(provenance_id)

    async def explain_fact(self, fact_id: str) -> dict[str, Any]:
        fact = await self.get_fact(fact_id)
        return {"fact": fact, **await self._provenance_chain(fact["provenance_id"])}

    @staticmethod
    def _fact_dict(model: FactModel | None) -> dict[str, Any]:
        if model is None:
            return {}
        result = serialize_model(model)
        result["value"] = result.pop("value_json")
        return result


def _fact_columns(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("value_json", data.get("value"))
    value_type = data.get("value_type", _infer_value_type(value))
    columns = dict(data)
    columns.pop("value", None)
    columns.pop("source_id", None)
    columns["value_json"] = json_safe(value)
    columns["value_type"] = value_type
    columns.setdefault("text_value", value if value_type == "string" and isinstance(value, str) else None)
    columns.setdefault("integer_value", value if value_type == "integer" and isinstance(value, int) else None)
    columns.setdefault("decimal_value", Decimal(str(value)) if value_type == "decimal" and value is not None else None)
    columns.setdefault("boolean_value", value if value_type == "boolean" and isinstance(value, bool) else None)
    return columns


def _infer_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, (float, Decimal)):
        return "decimal"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "collection"
    return "reference"
