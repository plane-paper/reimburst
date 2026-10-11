from shared.csv import safe_csv_cell


def test_safe_csv_cell_neutralizes_spreadsheet_formulas() -> None:
    assert safe_csv_cell("=HYPERLINK(\"https://example.test\")") == "'=HYPERLINK(\"https://example.test\")"
    assert safe_csv_cell("  +SUM(A1:A2)") == "'  +SUM(A1:A2)"
    assert safe_csv_cell("Lunch") == "Lunch"
    assert safe_csv_cell(1200) == "1200"
