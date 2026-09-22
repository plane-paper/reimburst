import os

from arq.connections import RedisSettings
from shared.categorization import CategorizationInput, OpenAiCategorizationProvider
from shared.enums import ExtractionStatus
from shared.models import Category, LineItem, Receipt
from shared.ocr import AzureDocumentIntelligenceOcrProvider, extraction_as_json
from shared.storage import object_storage_from_environment
from shared.taxonomy import UNCATEGORIZED
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def extract_receipt(_: dict[object, object], receipt_id: int, content_type: str) -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            receipt = await session.get(Receipt, receipt_id)
            if receipt is None:
                return
            if receipt.extraction_status is ExtractionStatus.SUCCEEDED:
                await categorize_receipt(_, receipt_id)
                return
            receipt.extraction_status = ExtractionStatus.PROCESSING
            receipt.extraction_error = None
            await session.commit()
            image_key = receipt.image_key

        try:
            image = await object_storage_from_environment().get(image_key)
            extraction = await AzureDocumentIntelligenceOcrProvider.from_environment().extract(
                image, content_type
            )
        except Exception as error:
            async with sessions() as session:
                receipt = await session.get(Receipt, receipt_id)
                if receipt is not None:
                    receipt.extraction_status = ExtractionStatus.FAILED
                    receipt.extraction_error = str(error)[:1000]
                    await session.commit()
            raise

        async with sessions() as session:
            receipt = await session.get(Receipt, receipt_id)
            if receipt is None:
                return
            receipt.merchant = extraction.merchant
            receipt.date = extraction.date
            receipt.currency = extraction.currency
            receipt.total_cents = extraction.total_cents
            receipt.tax_cents = extraction.tax_cents
            receipt.raw_extraction = extraction_as_json(extraction)
            receipt.extraction_status = ExtractionStatus.SUCCEEDED
            receipt.extraction_error = None
            await session.execute(delete(LineItem).where(LineItem.receipt_id == receipt.id))
            session.add_all(
                [
                    LineItem(
                        receipt_id=receipt.id,
                        description=item.description,
                        amount_cents=item.amount_cents,
                    )
                    for item in extraction.line_items
                ]
            )
            await session.commit()
        await categorize_receipt(_, receipt_id)
    finally:
        await engine.dispose()


async def categorize_receipt(_: dict[object, object], receipt_id: int) -> None:
    """Assign taxonomy categories after successful OCR without failing extraction."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            receipt = await session.get(Receipt, receipt_id)
            if receipt is None or receipt.extraction_status is not ExtractionStatus.SUCCEEDED:
                return
            if receipt.categorization_status is ExtractionStatus.SUCCEEDED:
                return
            receipt.categorization_status = ExtractionStatus.PROCESSING
            receipt.categorization_error = None
            line_items = list(
                await session.scalars(
                    select(LineItem).where(LineItem.receipt_id == receipt.id).order_by(LineItem.id)
                )
            )
            categories = list(
                await session.scalars(select(Category).where(Category.org_id.is_(None)))
            )
            await session.commit()

        taxonomy = [category.name for category in categories]
        category_by_name = {category.name: category.id for category in categories}
        if UNCATEGORIZED not in category_by_name:
            raise RuntimeError("The active taxonomy is missing uncategorized")
        results = await OpenAiCategorizationProvider.from_environment().categorize(
            [
                CategorizationInput(item.id, item.description, item.amount_cents)
                for item in line_items
            ],
            taxonomy,
        )

        async with sessions() as session:
            for result in results:
                item = await session.get(LineItem, result.line_item_id)
                if item is not None:
                    item.category_id = category_by_name[result.category]
                    item.needs_category_review = result.needs_review
            receipt = await session.get(Receipt, receipt_id)
            if receipt is not None:
                receipt.categorization_status = ExtractionStatus.SUCCEEDED
                receipt.categorization_error = None
            await session.commit()
    except Exception as error:
        async with sessions() as session:
            receipt = await session.get(Receipt, receipt_id)
            if receipt is not None:
                receipt.categorization_status = ExtractionStatus.FAILED
                receipt.categorization_error = str(error)[:1000]
                await session.commit()
        raise
    finally:
        await engine.dispose()


class WorkerSettings:
    functions = [extract_receipt, categorize_receipt]
    redis_settings = RedisSettings()
