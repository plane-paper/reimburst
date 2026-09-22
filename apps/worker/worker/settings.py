import os

from arq.connections import RedisSettings
from shared.enums import ExtractionStatus
from shared.models import LineItem, Receipt
from shared.ocr import AzureDocumentIntelligenceOcrProvider, extraction_as_json
from shared.storage import object_storage_from_environment
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def extract_receipt(_: dict[object, object], receipt_id: int, content_type: str) -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            receipt = await session.get(Receipt, receipt_id)
            if receipt is None or receipt.extraction_status is ExtractionStatus.SUCCEEDED:
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
    finally:
        await engine.dispose()


class WorkerSettings:
    functions = [extract_receipt]
    redis_settings = RedisSettings()
