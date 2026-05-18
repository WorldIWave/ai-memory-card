# Input: Markdown 文本（## Card 块格式）及 deck_name 字符串
# Output: ImportBundle，包含 DeckCreate 和解析出的 CardCreate 列表
# Role: Markdown 格式数据导入器，按 "## Card" 分块提取 Front/Back/Type 字段
# Note: 缺少 Front 或 Back 的块会被跳过；Type 缺省时默认为 "recall"
import re

from app.providers.importer.json_importer import ImportBundle
from app.schemas.card import CardCreate
from app.schemas.deck import DeckCreate


def import_markdown_cards(content: str, deck_name: str) -> ImportBundle:
    blocks = re.split(r"^##\s+Card", content, flags=re.MULTILINE)
    cards: list[CardCreate] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        front_lines = [l.split("Front:", 1)[1].strip() for l in lines if l.startswith("Front:")]
        back_lines = [l.split("Back:", 1)[1].strip() for l in lines if l.startswith("Back:")]
        if not front_lines or not back_lines:
            continue
        card_type = next((l.split("Type:", 1)[1].strip() for l in lines if l.startswith("Type:")), "recall")
        cards.append(CardCreate(deck_id=0, front=front_lines[0], back=back_lines[0], card_type=card_type, render_format="markdown"))
    return ImportBundle(deck=DeckCreate(name=deck_name), cards=cards)
