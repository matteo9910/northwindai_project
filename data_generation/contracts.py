from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from reportlab import rl_config
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Deterministic output: fix the PDF /ID and /CreationDate so regenerating the
# same contract produces byte-identical files (content-hash test depends on it).
rl_config.invariant = 1

DEFAULT_CONTRACT_DIR = Path("data/contracts")
BUYER_NAME = "NorthwindAI Trading B.V."
BUYER_REG = "Amsterdam Trade Register no. 7781002"
CURRENCY = "USD"
TERM_YEARS = 3
GOVERNING_LAW = "the laws of the Netherlands"
JURISDICTION = "the courts of Amsterdam"

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class ContractDocumentSpec:
    supplier_id: int
    company_name: str
    contract_number: str
    lead_time_days: int
    minimum_order_value: Decimal
    status: str
    start_date: str = "2020-01-01"
    end_date: str | None = None


CONTRACT_DOCUMENT_SPECS = (
    ContractDocumentSpec(
        supplier_id=1,
        company_name="Exotic Liquids",
        contract_number="CT-1-2020",
        lead_time_days=12,
        minimum_order_value=Decimal("500.00"),
        status="active",
    ),
    ContractDocumentSpec(
        supplier_id=3,
        company_name="Grandma Kelly's Homestead",
        contract_number="CT-3-2020",
        lead_time_days=30,
        minimum_order_value=Decimal("1200.00"),
        status="active",
    ),
    ContractDocumentSpec(
        supplier_id=4,
        company_name="Tokyo Traders",
        contract_number="CT-4-2020",
        lead_time_days=14,
        minimum_order_value=Decimal("900.00"),
        status="active",
    ),
    ContractDocumentSpec(
        supplier_id=7,
        company_name="Pavlova, Ltd.",
        contract_number="CT-7-2020",
        lead_time_days=10,
        minimum_order_value=Decimal("750.00"),
        status="active",
    ),
)


def generate_contract_pdfs(
    output_dir: Path = DEFAULT_CONTRACT_DIR,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for spec in CONTRACT_DOCUMENT_SPECS:
        path = output_dir / f"{spec.contract_number}.pdf"
        _write_contract_pdf(path, spec)
        paths.append(path)
    return paths


def hash_contract_files(paths: list[Path]) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ContractTitle",
            parent=base["Title"],
            fontSize=16,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "ContractSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor="#444444",
            spaceAfter=12,
        ),
        "article": ParagraphStyle(
            "ArticleHeading",
            parent=base["Heading2"],
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "ContractBody",
            parent=base["BodyText"],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "table_caption": ParagraphStyle(
            "TableCaption",
            parent=base["Normal"],
            fontSize=9,
            textColor="#555555",
            spaceBefore=2,
            spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            textColor="#777777",
        ),
    }


def _write_contract_pdf(path: Path, spec: ContractDocumentSpec) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"Master Supply and Logistics Agreement {spec.contract_number}",
        author=BUYER_NAME,
    )
    end_date = spec.end_date or "no fixed expiry (open-ended)"
    article = _article_factory(styles)
    delivery_title, delivery_flowables = _delivery_article(spec, styles)

    story = [
        Paragraph("MASTER SUPPLY AND LOGISTICS AGREEMENT", styles["title"]),
        Paragraph(f"Contract No. {spec.contract_number}", styles["subtitle"]),
        Paragraph(
            f"This Master Supply and Logistics Agreement (the "
            f"&quot;Agreement&quot;) is entered into between {BUYER_NAME} "
            f"({BUYER_REG}), acting as the &quot;Buyer&quot;, and "
            f"{spec.company_name}, acting as the &quot;Supplier&quot;. The "
            f"Agreement records contract {spec.contract_number} and its "
            f"current status is {spec.status}.",
            styles["body"],
        ),
        *article(
            "Recitals",
            [
                "WHEREAS the Buyer operates a multi-channel distribution "
                "business and sources goods for resale and replenishment;",
                "WHEREAS the Supplier is engaged in the production and supply "
                "of goods and possesses the capacity, facilities and logistics "
                "capabilities required to fulfil the Buyer's purchase orders;",
                "WHEREAS the parties wish to record the commercial, delivery "
                "and service terms governing their supply relationship.",
            ],
        ),
        *article(
            "1. Definitions",
            [
                "&quot;Purchase Order&quot; means a written or electronic order "
                "issued by the Buyer for goods under this Agreement. "
                "&quot;Order Acceptance&quot; means the Supplier's confirmation "
                "of a Purchase Order. &quot;Business Day&quot; means any day "
                "other than a Saturday, Sunday or public holiday at the place "
                "of dispatch.",
            ],
        ),
        *article(
            "2. Scope of Supply",
            [
                "The Supplier shall sell and deliver to the Buyer the goods "
                "described in each accepted Purchase Order, in the quantities "
                "and to the destinations specified, together with all "
                "ancillary handling, packing and dispatch services reasonably "
                "required for their delivery.",
            ],
        ),
    ]

    story.append(Paragraph(delivery_title, styles["article"]))
    story.extend(delivery_flowables)

    story.extend(
        article(
            "4. Order Process and Minimum Order Value",
            [
                "Purchase Orders are transmitted electronically and are deemed "
                "accepted unless the Supplier objects within two Business Days. "
                f"Each Purchase Order under this Agreement must meet a minimum "
                f"order value of {CURRENCY} {spec.minimum_order_value} before "
                "standard fulfilment commitments apply. Orders below that "
                "threshold may be consolidated or scheduled at the Supplier's "
                "discretion.",
            ],
        )
    )

    story.append(Paragraph("5. Pricing and Rate Schedule", styles["article"]))
    story.append(
        Paragraph(
            "Unit prices are net of VAT and are fixed for twelve months from "
            "the effective date, after which they are adjusted by the relevant "
            "consumer price index. The applicable rate schedule is set out "
            "below.",
            styles["body"],
        )
    )
    story.append(_pricing_table(spec))
    story.append(
        Paragraph("Table 1 - Rate schedule (per unit).", styles["table_caption"])
    )

    story.append(PageBreak())

    story.append(Paragraph("6. Volume Forecast", styles["article"]))
    story.append(
        Paragraph(
            "The following non-binding monthly volume profile is provided for "
            "capacity planning. A sustained deviation above ten percent (10%) "
            "from these reference volumes entitles either party to request a "
            "review of the commercial terms.",
            styles["body"],
        )
    )
    story.append(_volume_table(spec))
    story.append(
        Paragraph(
            "Table 2 - Indicative monthly volume profile (units).",
            styles["table_caption"],
        )
    )

    story.extend(
        article(
            "7. Quality and Acceptance",
            [
                "The Supplier warrants that goods conform to the agreed "
                "specifications and are free from defects in materials and "
                "workmanship. The Buyer may inspect goods on receipt and reject "
                "non-conforming goods within ten Business Days of delivery.",
            ],
        )
    )
    story.extend(
        article(
            "8. Liability and Risk Allocation",
            [
                "Risk in the goods passes to the Buyer on delivery to the "
                "agreed destination. Save in cases of wilful misconduct or "
                "gross negligence, the Supplier's aggregate liability for loss "
                "of or damage to goods shall not exceed 8.33 units of account "
                "per kilogram of gross weight of the goods affected. Liability "
                "for delay, where a delivery date has been expressly agreed, "
                "shall not exceed twice the charges for the affected service.",
            ],
        )
    )
    story.extend(
        article(
            "9. Insurance",
            [
                "The Supplier shall maintain, with reputable insurers, "
                "all-risks cargo insurance covering the goods during carriage "
                "and adequate public and product liability cover, and shall "
                "provide evidence of such cover on request.",
            ],
        )
    )
    story.extend(
        article(
            "10. Term, Renewal and Termination",
            [
                f"This Agreement takes effect on {spec.start_date} and "
                f"continues for {TERM_YEARS} years ({end_date}). It renews "
                "automatically for successive equal periods unless either party "
                "gives six months' written notice. As at the date of this "
                f"Agreement the contract status is {spec.status}. Either party "
                "may terminate for material, unremedied breach on three months' "
                "written notice.",
            ],
        )
    )
    story.extend(
        article(
            "11. Governance, Reporting and Service Levels",
            [
                "The parties shall meet periodically to review service "
                "performance against the agreed service levels, including "
                "on-time delivery, order accuracy and inventory reconciliation, "
                "and shall agree corrective actions for any shortfall.",
            ],
        )
    )
    story.extend(
        article(
            "12. Force Majeure",
            [
                "Neither party is liable for failure to perform caused by "
                "events beyond its reasonable control, including natural "
                "disasters, conflict, or transport disruption, provided the "
                "affected party notifies the other promptly and mitigates the "
                "impact.",
            ],
        )
    )
    story.extend(
        article(
            "13. Governing Law and Jurisdiction",
            [
                f"This Agreement is governed by {GOVERNING_LAW} and the parties "
                f"submit to the exclusive jurisdiction of {JURISDICTION}.",
            ],
        )
    )

    story.append(Spacer(1, 18))
    story.append(Paragraph("14. Signatures", styles["article"]))
    story.append(_signature_table(spec))
    story.append(
        Paragraph(
            f"Controlled-scenario contract {spec.contract_number} - "
            f"{BUYER_NAME} and {spec.company_name}.",
            styles["footer"],
        )
    )

    doc.build(story)


def _article_factory(styles):
    def article(heading: str, paragraphs: list[str]) -> list:
        flowables = [Paragraph(heading, styles["article"])]
        flowables.extend(Paragraph(text, styles["body"]) for text in paragraphs)
        return flowables

    return article


def _delivery_article(
    spec: ContractDocumentSpec,
    styles,
) -> tuple[str, list]:
    """Return the delivery article title and flowables.

    Lead-time wording is graduated by supplier to exercise semantic retrieval:
    Pavlova is explicit, Tokyo and Grandma Kelly's embed the figure in prose,
    and Exotic Liquids avoids the literal phrase 'lead time' entirely.
    """
    body = styles["body"]
    caption = styles["table_caption"]
    if spec.supplier_id == 4:
        title = "3. Delivery Terms"
        prose = (
            "The Supplier shall prepare accepted Purchase Orders for dispatch "
            "through its standard replenishment lane. For planning purposes, "
            "the delivery lead time is fourteen business days from Order "
            "Acceptance, provided the requested items are available for export. "
            "Expedited handling may be agreed in writing for individual orders."
        )
        sla = [
            ["Service level", "Target"],
            ["Order acknowledgement", "1 business day"],
            ["Standard delivery lead time", "14 business days"],
            ["On-time delivery", "97%"],
        ]
    elif spec.supplier_id == 7:
        title = "3. Delivery Lead Time"
        prose = (
            "The Supplier commits to a delivery lead time of 10 business days "
            "for standard replenishment orders, measured from Order Acceptance "
            "to dispatch from the Supplier's facility."
        )
        sla = [
            ["Service level", "Target"],
            ["Order acknowledgement", "1 business day"],
            ["Delivery lead time", "10 business days"],
            ["On-time delivery", "98%"],
        ]
    elif spec.supplier_id == 3:
        title = "3. Delivery Terms"
        prose = (
            "The Supplier shall complete standard delivery within thirty "
            "business days after Order Acceptance and inventory confirmation. "
            "Seasonal preserves and small-batch goods may be scheduled in "
            "production windows agreed with the Buyer."
        )
        sla = [
            ["Service level", "Target"],
            ["Order acknowledgement", "2 business days"],
            ["Standard delivery", "within 30 business days"],
            ["On-time delivery", "95%"],
        ]
    else:
        title = "3. Fulfilment and Delivery Window"
        prose = (
            "The Supplier applies a standard delivery window of 12 business "
            "days from confirmed Order Acceptance. During seasonal demand "
            "peaks the fulfilment period may require prior scheduling with the "
            "account team, and the parties shall agree a revised dispatch plan "
            "where necessary."
        )
        sla = [
            ["Service level", "Target"],
            ["Order acknowledgement", "2 business days"],
            ["Standard delivery window", "12 business days"],
            ["Peak-season fulfilment period", "by prior arrangement"],
        ]

    table = _styled_table(sla, col_widths=[3.2 * inch, 3.0 * inch], header=True)
    return title, [
        Paragraph(prose, body),
        table,
        Paragraph(
            "Table - Delivery service levels.",
            caption,
        ),
    ]


def _pricing_table(spec: ContractDocumentSpec) -> Table:
    base = 10 + spec.supplier_id
    categories = (
        ("Standard replenishment line", "case"),
        ("Priority lane handling", "case"),
        ("Pallet build and wrap", "pallet"),
        ("Cross-dock consolidation", "shipment"),
    )
    rows = [["Service / category", "Unit", f"Unit price ({CURRENCY})"]]
    for index, (category, unit) in enumerate(categories):
        price = base + index * 5
        rows.append([category, unit, f"{price}.00"])
    return _styled_table(
        rows,
        col_widths=[3.4 * inch, 1.4 * inch, 1.4 * inch],
        header=True,
    )


def _volume_table(spec: ContractDocumentSpec) -> Table:
    base = spec.supplier_id * 100
    rows = [["Month", "Inbound", "Outbound", "Closing stock"]]
    for index, month in enumerate(MONTHS):
        inbound = base + index * 10
        outbound = base + index * 8
        stock = 500 + spec.supplier_id * 50 + index * 5
        rows.append([month, str(inbound), str(outbound), str(stock)])
    return _styled_table(
        rows,
        col_widths=[1.8 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch],
        header=True,
    )


def _signature_table(spec: ContractDocumentSpec) -> Table:
    rows = [
        ["For the Buyer", "For the Supplier"],
        [BUYER_NAME, spec.company_name],
        ["Name: ____________________", "Name: ____________________"],
        ["Title: ____________________", "Title: ____________________"],
        ["Date: ____________________", "Date: ____________________"],
    ]
    return _styled_table(rows, col_widths=[3.1 * inch, 3.1 * inch], header=True)


def _styled_table(rows, col_widths, header: bool) -> Table:
    table = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, "#999999"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.extend(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), "#e6e6e6"),
            ]
        )
    table.setStyle(TableStyle(style))
    return table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic supplier contract PDFs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_CONTRACT_DIR,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = generate_contract_pdfs(output_dir=args.output_dir)
    for name, digest in hash_contract_files(paths).items():
        print(f"{name} {digest}")


if __name__ == "__main__":
    main()
