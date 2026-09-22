from shared.categorization import CategorizationInput, categorization_schema, parse_categorizations
from shared.taxonomy import DEFAULT_TAXONOMY, UNCATEGORIZED


def test_schema_constrains_categories_to_the_taxonomy() -> None:
    schema = categorization_schema(list(DEFAULT_TAXONOMY))
    assert schema["properties"]["items"]["items"]["properties"]["category"]["enum"] == list(
        DEFAULT_TAXONOMY
    )


def test_invalid_or_missing_llm_results_fall_back_to_reviewable_uncategorized() -> None:
    items = [CategorizationInput(1, "Taxi", 1200), CategorizationInput(2, "Mystery", 500)]
    results = parse_categorizations(
        {"items": [{"line_item_id": 1, "category": "transport", "confidence": "high"}]},
        items,
        list(DEFAULT_TAXONOMY),
    )
    assert results[0].category == "transport"
    assert not results[0].needs_review
    assert results[1].category == UNCATEGORIZED
    assert results[1].needs_review
