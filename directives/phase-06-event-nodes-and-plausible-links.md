# Phase 06 - Event Nodes & Complaint Issue Events / Query Ladder Step 3

> Revised Phase 06 directive. This phase must align with the actual Supabase
> dataset: `erp_docs.customer_communications.subject` already acts as the
> structured complaint classification produced by an upstream classifier. Do not
> infer complaint issue type from `body` keyword matching in this phase.

---

## Objective

Deliver the third query ladder step end to end by extending the Knowledge Layer
with operational shipment delay Event Nodes and classified complaint issue Event
Nodes:

- `ShipmentDelayEvent` is derived from `erp_core.shipments.delay_days > 0`.
- `CustomerComplaintEvent` is derived from
  `erp_docs.customer_communications` rows where
  `contact_reason = 'complaint'`.
- `CustomerComplaintEvent.subject` is treated as the source classification and
  mapped to a canonical `issue_type`.
- Specialized complaint issue Event Nodes are derived from that classification:
  `DeliveryDelayComplaintEvent`, `PackagingQualityComplaintEvent`, and
  `ProductQualityComplaintEvent`.
- `DeliveryDelayComplaintEvent` is created only when the complaint is classified
  as `delivery_delay` and a matching `ShipmentDelayEvent` exists for the same
  `order_id` and `product_id`.
- `PackagingQualityComplaintEvent` and `ProductQualityComplaintEvent` are
  created for classified complaints even when no shipment delay exists.

This phase replaces the earlier `POSSIBLY_RELATED_TO` design for the controlled
dataset. Plausible relationships remain a valid ADR 0012 pattern for future
unclassified or low-confidence cases, but they are not the primary Phase 06
model because the current data already contains a structured issue
classification.

---

## Ground Truth From Supabase

The current `erp_docs.customer_communications` table contains exactly three
complaint subjects:

```text
Late delivery affected replenishment -> delivery_delay
Packaging quality issue -> packaging_quality
Product quality below expectation -> product_quality
```

The `subject` column simulates the production output of a complaint classifier.
The `body` column is supporting evidence text only. It is currently not varied
enough to be a realistic semantic-classification oracle, because each complaint
subject has one repeated body template.

Phase 06 must therefore use:

```text
contact_reason = 'complaint'
subject -> issue_type
```

not:

```text
body contains "late" or "delay"
```

---

## Design Decisions

1. **Subject is the classification source.** `subject` is the structured issue
   classification already present in the Operational Source of Truth. Persist
   both the original `subject` and normalized `issue_type` on
   `CustomerComplaintEvent`.

2. **Use a dedicated issue type mapping module.** Keep the mapping in
   `backend/graph/complaint_issue_types.py`, not inline in the large projection
   module and not in a PostgreSQL lookup table for this PoC.

3. **Keep `CustomerComplaintEvent` as the base event.** It represents the source
   complaint communication. Specialized issue Event Nodes are derived from it and
   connected with `CLASSIFIED_AS`.

4. **Create specialized complaint issue Event Nodes.**
   - `DeliveryDelayComplaintEvent`
   - `PackagingQualityComplaintEvent`
   - `ProductQualityComplaintEvent`

5. **Context links are direct and auditable.** Specialized issue Event Nodes
   should carry direct context relationships when the source FK exists:
   `RAISED_BY`, `ABOUT_ORDER`, and `ABOUT_PRODUCT`.

6. **Delivery delay complaints require operational support.**
   `DeliveryDelayComplaintEvent` requires:
   - `CustomerComplaintEvent.issue_type = "delivery_delay"`
   - same `order_id`
   - same `product_id`
   - a `ShipmentDelayEvent` exists on the shipment for that order

   Do not require a time-window rule in this phase; the classification already
   comes from `subject`.

7. **Supported delay evidence is explicit.** Link:

   ```cypher
   (:DeliveryDelayComplaintEvent)-[:SUPPORTED_BY_DELAY]->(:ShipmentDelayEvent)
   ```

   This replaces `POSSIBLY_RELATED_TO` for Phase 06.

8. **No event tables in PostgreSQL.** All Event Nodes remain born in Neo4j only
   (ADR 0004). PostgreSQL remains the Operational Source of Truth for raw facts
   and source classifications.

9. **No LLM or classifier runtime in Phase 06.** The production analogue is an
   upstream classifier that writes the structured issue classification. In this
   PoC, `subject` stands in for that classifier output.

10. **Route is still asserted.** The ladder route remains `graph_only`; the
    LangGraph Query Router is later.

---

## Functional Requirements

After this phase the system must:

1. Project `Supplier`, `Product`, `Customer`, `Order`, and `Shipment` nodes plus
   explicit FK-based relationships `SUPPLIES`, `PLACED`, `CONTAINS`, and
   `FULFILLED_BY`, all with Graph Provenance.

2. Derive `ShipmentDelayEvent` nodes from `erp_core.shipments` rows with
   `delay_days > 0`, linked from `Shipment` with `HAS_DELAY_EVENT`.

3. Derive `CustomerComplaintEvent` nodes from complaint communications only:

   ```sql
   contact_reason = 'complaint'
   ```

   Each node must include `subject`, `issue_type`, `body`, `sentiment`,
   `channel`, `occurred_at`, source identifiers, and Graph Provenance.

4. Derive one specialized issue Event Node per classified complaint:
   - `DeliveryDelayComplaintEvent` only when supported by a matching
     `ShipmentDelayEvent`.
   - `PackagingQualityComplaintEvent` for `issue_type = "packaging_quality"`.
   - `ProductQualityComplaintEvent` for `issue_type = "product_quality"`.

5. Link each `CustomerComplaintEvent` to its specialized Event Node with
   `CLASSIFIED_AS`.

6. Link specialized Event Nodes to available business context with
   `RAISED_BY`, `ABOUT_ORDER`, and `ABOUT_PRODUCT`.

7. Link `DeliveryDelayComplaintEvent` to the supporting `ShipmentDelayEvent`
   with `SUPPORTED_BY_DELAY`.

8. Remove Phase 06 creation of `POSSIBLY_RELATED_TO`. Tests should assert that
   the revised Phase 06 graph does not rely on that relationship for complaint
   issue classification.

9. Update the Cypher validator allowlists with only the new labels and
   relationship types required by this phase:
   - Labels: `DeliveryDelayComplaintEvent`,
     `PackagingQualityComplaintEvent`, `ProductQualityComplaintEvent`
   - Relationships: `CLASSIFIED_AS`, `SUPPORTED_BY_DELAY`

10. Update Step 3 to answer:

    ```text
    Which Tokyo Traders orders had shipment delays with delay complaints?
    ```

    The traversal must use the graph, not direct PostgreSQL joins, and return
    delayed orders that also have `DeliveryDelayComplaintEvent` support.

11. Include tests proving packaging and product-quality issue events exist and
    are linked to products/orders/customers. No dedicated endpoint is required
    for these issue types in Phase 06.

---

## Expected Graph Shape

Operational delay path:

```text
Supplier -SUPPLIES-> Product <-CONTAINS- Order
Order -FULFILLED_BY-> Shipment -HAS_DELAY_EVENT-> ShipmentDelayEvent
```

Complaint base event:

```text
CustomerComplaintEvent -RAISED_BY-> Customer
CustomerComplaintEvent -ABOUT_ORDER-> Order
CustomerComplaintEvent -ABOUT_PRODUCT-> Product
```

Classified issue event:

```text
CustomerComplaintEvent -CLASSIFIED_AS-> DeliveryDelayComplaintEvent
DeliveryDelayComplaintEvent -RAISED_BY-> Customer
DeliveryDelayComplaintEvent -ABOUT_ORDER-> Order
DeliveryDelayComplaintEvent -ABOUT_PRODUCT-> Product
DeliveryDelayComplaintEvent -SUPPORTED_BY_DELAY-> ShipmentDelayEvent
```

Packaging/product quality issue events follow the same `CLASSIFIED_AS` and
context-link pattern, without `SUPPORTED_BY_DELAY`.

---

## Implementation Notes

- Use idempotent `MERGE` keyed by source communication identity for specialized
  complaint issue Event Nodes. Example keys:
  - `DeliveryDelayComplaintEvent {communication_id}`
  - `PackagingQualityComplaintEvent {communication_id}`
  - `ProductQualityComplaintEvent {communication_id}`
- Preserve Graph Provenance on every new node and relationship:
  `source_system`, `source_schema`, `source_table`, `source_pk`,
  `projection_version`, `rule_name`, `rule_version`, and `derived_from` where
  applicable.
- Use `rule_name`s that describe the derivation:
  - `delivery_delay_complaint_event`
  - `packaging_quality_complaint_event`
  - `product_quality_complaint_event`
  - `complaint_classified_as_issue`
  - `delivery_complaint_supported_by_delay`
- Keep projection batched and schema-indexed; live tests must complete against
  the full Supabase dataset.

---

## Tests

Update or add tests proving:

- `CustomerComplaintEvent.issue_type` is populated from `subject`.
- `body` is preserved as evidence but not used as the primary classifier.
- `DeliveryDelayComplaintEvent` count matches classified late-delivery
  complaints that have matching shipment delay support.
- `DeliveryDelayComplaintEvent` is linked via `SUPPORTED_BY_DELAY` to
  `ShipmentDelayEvent`.
- `PackagingQualityComplaintEvent` and `ProductQualityComplaintEvent` exist and
  have `CLASSIFIED_AS`, `ABOUT_ORDER`, `ABOUT_PRODUCT`, and `RAISED_BY` context.
- `POSSIBLY_RELATED_TO` is not created by the revised Phase 06 projection.
- Step 3 answer matches PostgreSQL read-back for Tokyo Traders delayed orders
  with classified delivery-delay complaints.
- `pytest` and `ruff check .` pass with live tests when Supabase and Neo4j are
  reachable.

---

## Out of Scope

- Building or calling a real ML/LLM classifier.
- Creating PostgreSQL event tables.
- Qdrant, embeddings, contract retrieval, and ContractTermEvents.
- LangGraph route classification.
- Dedicated endpoints for packaging/product-quality issue analysis.
- Human review workflows or operational discrepancy events.
