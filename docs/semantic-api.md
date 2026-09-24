# Semantic API

Clients use operation-oriented endpoints rather than table-shaped requests.

| Operation | Endpoint | Purpose |
|---|---|---|
| evaluate | POST /api/v1/semantic/evaluate | global facts + active rules + applicant/query context |
| simulate | POST /api/v1/semantic/simulate | base result versus immutable overlays |
| explain | GET /api/v1/semantic/explain/{result_id} | derived-to-source explanation tree |
| program | GET /api/v1/semantic/programs/{program_id} | program semantic projection |
| curriculum | GET /api/v1/semantic/programs/{program_id}/curriculum | curriculum edge projection |

Evaluation accepts ephemeral applicant data. Setting persist false keeps both
the applicant and result in memory for the request. Persist true materializes
DerivedValue with its context snapshot, trace and dependency edges. Applicant
data is never inserted into the global facts table.

The response contains result_id when materialized, derived_type, value,
matched_rules, rule_versions, explanation_summary, trace, engine version and
ontology version. Before/after simulation includes delta and an empty
persisted_changes list.

Consumer clients are read-only. There is no semantic route for rule or
ontology activation. Admin mutation paths require an elevated role and are
separated by router tags and application services.

