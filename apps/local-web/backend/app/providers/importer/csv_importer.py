# Input: CSV 文本（含 front/back/card_type 列）及 deck_name 字符串
# Output: ImportBundle，包含 DeckCreate 和 CardCreate 列表
# Role: CSV 格式数据导入器，将表格数据转换为系统内部卡片结构
# Note: 必须包含 front 和 back 列；card_type 缺省时默认为 "recall"
import csv
from io import StringIO

from app.providers.importer.json_importer import ImportBundle
from app.schemas.card import CardCreate
from app.schemas.deck import DeckCreate


def import_csv_cards(content: str, deck_name: str) -> ImportBundle:
    rows = csv.DictReader(StringIO(content))
    cards = [
        CardCreate(
            deck_id=0,
            front=row["front"],
            back=row["back"],
            card_type=row.get("card_type") or "recall",
            render_format="markdown",
        )
        for row in rows
    ]
    return ImportBundle(deck=DeckCreate(name=deck_name), cards=cards)
