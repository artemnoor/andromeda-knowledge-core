# ADR 0004: Facts and Derived Knowledge are separate

Status: accepted.

A Fact is an accepted source-backed assertion. A DerivedValue is a rebuildable
calculation from facts, rules, ontology and context. Separate tables prevent a
calculation from masquerading as evidence, support targeted invalidation and
make provenance/explanation honest.

