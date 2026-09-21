from shared.ocr import money_to_cents, parse_azure_receipt


def test_money_to_cents_uses_decimal_not_float() -> None:
    assert money_to_cents("12.345") == 1235
    assert money_to_cents("0.29") == 29


def test_parse_azure_receipt_extracts_integer_money_and_items() -> None:
    result = {
        "analyzeResult": {
            "documents": [
                {
                    "fields": {
                        "MerchantName": {"content": "Corner Store"},
                        "TransactionDate": {"content": "2026-09-20"},
                        "Total": {"valueCurrency": {"amount": 10.5, "currencyCode": "USD"}},
                        "TotalTax": {"valueCurrency": {"amount": 0.5, "currencyCode": "USD"}},
                        "Items": {
                            "valueArray": [
                                {
                                    "valueObject": {
                                        "Description": {"content": "Lunch"},
                                        "TotalPrice": {"valueCurrency": {"amount": 10}},
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        }
    }

    extraction = parse_azure_receipt(result)

    assert extraction.merchant == "Corner Store"
    assert extraction.date and extraction.date.isoformat() == "2026-09-20"
    assert extraction.currency == "USD"
    assert extraction.total_cents == 1050
    assert extraction.tax_cents == 50
    items = [(item.description, item.amount_cents) for item in extraction.line_items]
    assert items == [("Lunch", 1000)]
