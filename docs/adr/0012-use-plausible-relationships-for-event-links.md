# Use plausible relationships for event links

Derived links between business events, such as a shipment delay and a customer complaint, will use plausible relationship semantics rather than definitive causality unless the source evidence explicitly supports causation. For example, `ShipmentDelayEvent POSSIBLY_RELATED_TO CustomerComplaintEvent` is preferred over `ShipmentDelayEvent CAUSED CustomerComplaintEvent`.

**Consequences**: Event links can carry confidence, matching reason, time window, and evidence references, allowing the agent to explain correlations without overstating certainty. Controlled scenarios may include stronger evidence, such as complaint reason codes, but the graph still preserves the distinction between plausibility and proof.
