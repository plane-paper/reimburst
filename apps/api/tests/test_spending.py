from datetime import date

from app.spending import SpendingItem, report_for


def test_spending_report_groups_by_category_and_currency() -> None:
    report = report_for(
        [
            SpendingItem(
                receipt_id=1,
                line_item_id=1,
                merchant="Cafe",
                receipt_date=date(2026, 9, 1),
                currency="USD",
                description="Lunch",
                amount_cents=1200,
                category="food",
            ),
            SpendingItem(
                receipt_id=1,
                line_item_id=2,
                merchant="Cafe",
                receipt_date=date(2026, 9, 1),
                currency="USD",
                description="Coffee",
                amount_cents=300,
                category="food",
            ),
            SpendingItem(
                receipt_id=2,
                line_item_id=3,
                merchant="Hotel",
                receipt_date=date(2026, 9, 2),
                currency="CAD",
                description="Room",
                amount_cents=25000,
                category="hotel",
            ),
        ],
        "category",
    )
    assert report.total_cents == 26500
    assert [group.model_dump() for group in report.groups] == [
        {"name": "hotel", "currency": "CAD", "total_cents": 25000},
        {"name": "food", "currency": "USD", "total_cents": 1500},
    ]
