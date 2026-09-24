# Bi-temporal model

Facts, relations and rules distinguish two independent clocks:

- valid time: when a statement is true in the modeled world;
- transaction time: when Andromeda accepted or knew that statement.

Intervals are half-open: [from, to). Null end means open-ended. Domain and
database checks reject an end that is not after its start.

~~~mermaid
timeline
  title Same statement on two axes
  2027 : valid_from
  2028 : Andromeda receives observation
  2029 : transaction-time correction
~~~

A current query uses the current transaction version. A valid-time query adds
valid_at predicates. A historical knowledge query adds known_at predicates.
These filters are independent, so a statement may be valid in 2027 but not
known by Andromeda until 2028.

The repository applies the same semantics to facts and relations. Rule versions
also carry valid and transaction columns and are filtered when the computation
context supplies as-of timestamps. Derived result keys include the query
context and exact ontology/rule snapshot, so a historical result cannot
silently reuse a current projection.

Normal corrections close the previous transaction interval and insert a new
canonical version. Historical rows are retained; normal APIs do not delete
knowledge.

