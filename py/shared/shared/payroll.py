"""Provider boundary and deterministic CSV fallback for organization payouts."""

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Protocol


@dataclass(frozen=True)
class PayoutExport:
    """Frozen information supplied to a payroll export provider."""

    request_id: int
    employee_email: str
    amount_cents: int
    currency: str
    idempotency_key: str


class PayrollProvider(Protocol):
    """Dispatch approved payouts without exposing provider details to the API."""

    name: str

    def export(self, payouts: list[PayoutExport]) -> bytes: ...


class CsvPayrollProvider:
    """Manual-payroll fallback which emits a stable, machine-readable CSV."""

    name = "csv"

    def export(self, payouts: list[PayoutExport]) -> bytes:
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            ["request_id", "employee_email", "amount_cents", "currency", "idempotency_key"]
        )
        for payout in payouts:
            writer.writerow(
                [
                    payout.request_id,
                    payout.employee_email,
                    payout.amount_cents,
                    payout.currency,
                    payout.idempotency_key,
                ]
            )
        return output.getvalue().encode()
