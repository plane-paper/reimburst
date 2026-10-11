"""Safe serialization helpers for CSV files opened by spreadsheet programs."""


def safe_csv_cell(value: object) -> str:
    """Return a cell that spreadsheet applications cannot evaluate as a formula."""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text
