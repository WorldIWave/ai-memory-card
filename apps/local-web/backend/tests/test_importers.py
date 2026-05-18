# Input: 纯字符串/字典载荷（json/csv/markdown）  |  Output: ImportResult（deck + cards 列表）
# Role: 三种导入器（JSON/CSV/Markdown）的单元测试，不依赖数据库或 HTTP 层
# Note: 无 fixture 依赖；markdown 解析依赖 "Front:/Back:/Type:" 格式的 H2 块
# Usage: pytest tests/test_importers.py
from app.providers.importer.csv_importer import import_csv_cards
from app.providers.importer.json_importer import import_json_cards
from app.providers.importer.markdown_importer import import_markdown_cards


def test_import_json_cards_reads_internal_schema() -> None:
    payload = {
        "deck": {"name": "ML"},
        "cards": [{"card_type": "recall", "front": "f", "back": "b", "render_format": "markdown"}],
    }

    result = import_json_cards(payload)

    assert result.deck.name == "ML"
    assert len(result.cards) == 1
    assert result.cards[0].front == "f"


def test_import_csv_cards_reads_rows() -> None:
    content = "front,back,card_type\nWhat is AI?,Artificial intelligence,recall\n"

    result = import_csv_cards(content, deck_name="Intro")

    assert result.deck.name == "Intro"
    assert result.cards[0].front == "What is AI?"
    assert result.cards[0].back == "Artificial intelligence"


def test_import_markdown_cards_reads_question_answer_blocks() -> None:
    content = "## Card\nFront: What is RAG?\nBack: Retrieval augmented generation.\nType: recall\n"

    result = import_markdown_cards(content, deck_name="NLP")

    assert result.deck.name == "NLP"
    assert result.cards[0].back == "Retrieval augmented generation."
