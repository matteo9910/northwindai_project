from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComplaintIssueType:
    subject: str
    issue_type: str
    event_label: str
    rule_name: str


DELIVERY_DELAY = ComplaintIssueType(
    subject="Late delivery affected replenishment",
    issue_type="delivery_delay",
    event_label="DeliveryDelayComplaintEvent",
    rule_name="delivery_delay_complaint_event",
)
PACKAGING_QUALITY = ComplaintIssueType(
    subject="Packaging quality issue",
    issue_type="packaging_quality",
    event_label="PackagingQualityComplaintEvent",
    rule_name="packaging_quality_complaint_event",
)
PRODUCT_QUALITY = ComplaintIssueType(
    subject="Product quality below expectation",
    issue_type="product_quality",
    event_label="ProductQualityComplaintEvent",
    rule_name="product_quality_complaint_event",
)

COMPLAINT_ISSUE_TYPES = (
    DELIVERY_DELAY,
    PACKAGING_QUALITY,
    PRODUCT_QUALITY,
)
COMPLAINT_ISSUE_TYPES_BY_SUBJECT = {
    issue.subject: issue for issue in COMPLAINT_ISSUE_TYPES
}


def complaint_issue_type_for_subject(subject: str | None) -> ComplaintIssueType | None:
    if subject is None:
        return None
    return COMPLAINT_ISSUE_TYPES_BY_SUBJECT.get(subject)
