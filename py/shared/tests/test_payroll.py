from shared.payroll import CsvPayrollProvider, PayoutExport


def test_csv_provider_emits_integer_money_and_idempotency_key() -> None:
    payload = CsvPayrollProvider().export(
        [
            PayoutExport(
                request_id=17,
                employee_email="employee@example.test",
                amount_cents=12345,
                currency="USD",
                idempotency_key="csv:payout:17",
            )
        ]
    )

    assert payload.decode() == (
        "request_id,employee_email,amount_cents,currency,idempotency_key\r\n"
        "17,employee@example.test,12345,USD,csv:payout:17\r\n"
    )
