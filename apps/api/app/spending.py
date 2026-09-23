import csv
from collections import defaultdict
from datetime import date
from io import StringIO
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from shared.enums import UserRole
from shared.models import Category, LineItem, Receipt, User
from sqlalchemy import Select, select

from app.database import session_factory
from app.receipts import development_owner_id

router = APIRouter(prefix="/spending", tags=["spending"])


class SpendingItem(BaseModel):
    receipt_id: int
    line_item_id: int
    merchant: str | None
    receipt_date: date | None
    currency: str | None
    description: str
    amount_cents: int
    category: str | None


class SpendingHistory(BaseModel):
    items: list[SpendingItem]


class SpendingGroup(BaseModel):
    name: str
    currency: str | None
    total_cents: int


class SpendingReport(BaseModel):
    group_by: Literal["category", "merchant", "date"]
    groups: list[SpendingGroup]
    total_cents: int


def spending_statement(
    owner_id: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> Select[tuple[Receipt, LineItem, str | None]]:
    statement = (
        select(Receipt, LineItem, Category.name)
        .join(LineItem, LineItem.receipt_id == Receipt.id)
        .outerjoin(Category, LineItem.category_id == Category.id)
        .where(Receipt.owner_id == owner_id, Receipt.confirmed_at.is_not(None))
        .order_by(Receipt.date.desc().nullslast(), Receipt.id.desc(), LineItem.id)
    )
    if start_date is not None:
        statement = statement.where(Receipt.date >= start_date)
    if end_date is not None:
        statement = statement.where(Receipt.date <= end_date)
    if category is not None:
        statement = statement.where(Category.name == category)
    if merchant is not None:
        statement = statement.where(Receipt.merchant.ilike(f"%{merchant}%"))
    return statement


async def personal_spending_items(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> list[SpendingItem]:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    owner_id = await development_owner_id()
    async with session_factory()() as session:
        owner = await session.get(User, owner_id)
        if owner is None or owner.role is not UserRole.INDIVIDUAL:
            raise HTTPException(
                status_code=403, detail="Personal spending is only available to individuals"
            )
        rows = (
            await session.execute(
                spending_statement(
                    owner_id,
                    start_date=start_date,
                    end_date=end_date,
                    category=category,
                    merchant=merchant,
                )
            )
        ).all()
    return [
        SpendingItem(
            receipt_id=receipt.id,
            line_item_id=item.id,
            merchant=receipt.merchant,
            receipt_date=receipt.date,
            currency=receipt.currency,
            description=item.description,
            amount_cents=item.amount_cents,
            category=category_name,
        )
        for receipt, item, category_name in rows
    ]


def report_for(
    items: list[SpendingItem], group_by: Literal["category", "merchant", "date"]
) -> SpendingReport:
    totals: defaultdict[tuple[str, str | None], int] = defaultdict(int)
    for item in items:
        if group_by == "category":
            name = item.category or "uncategorized"
        elif group_by == "merchant":
            name = item.merchant or "Unknown merchant"
        else:
            name = item.receipt_date.isoformat() if item.receipt_date else "Unknown date"
        totals[(name, item.currency)] += item.amount_cents
    groups = [
        SpendingGroup(name=name, currency=currency, total_cents=total)
        for (name, currency), total in sorted(
            totals.items(), key=lambda entry: (-entry[1], entry[0])
        )
    ]
    return SpendingReport(
        group_by=group_by,
        groups=groups,
        total_cents=sum(item.amount_cents for item in items),
    )


@router.get("/history", response_model=SpendingHistory)
async def get_spending_history(
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> SpendingHistory:
    return SpendingHistory(
        items=await personal_spending_items(
            start_date=start_date,
            end_date=end_date,
            category=category,
            merchant=merchant,
        )
    )


@router.get("/report", response_model=SpendingReport)
async def get_spending_report(
    group_by: Literal["category", "merchant", "date"] = "category",
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> SpendingReport:
    return report_for(
        await personal_spending_items(
            start_date=start_date,
            end_date=end_date,
            category=category,
            merchant=merchant,
        ),
        group_by,
    )


@router.get("/export.csv", response_class=Response)
async def export_spending_csv(
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
) -> Response:
    items = await personal_spending_items(
        start_date=start_date, end_date=end_date, category=category, merchant=merchant
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "receipt_id",
            "line_item_id",
            "date",
            "merchant",
            "description",
            "category",
            "amount_cents",
            "currency",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.receipt_id,
                item.line_item_id,
                item.receipt_date.isoformat() if item.receipt_date else "",
                item.merchant or "",
                item.description,
                item.category or "",
                item.amount_cents,
                item.currency or "",
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="spending-history.csv"'},
    )
