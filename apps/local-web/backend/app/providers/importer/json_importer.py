# Input: 包含 deck 和 cards 字段的 JSON dict  |  Output: ImportBundle dataclass
# Role: JSON 格式数据导入器，同时定义 ImportBundle 数据结构供其他导入器复用
# Note: ImportBundle 是所有 importer 的统一返回类型，cards 中 deck_id 暂设为 0
# Usage: import_json_cards(payload) 直接调用；其他导入器导入 ImportBundle 类型
from dataclasses import dataclass

from app.schemas.card import CardCreate
from app.schemas.deck import DeckCreate


@dataclass
class ImportBundle:
    deck: DeckCreate
    cards: list[CardCreate]


def import_json_cards(payload: dict) -> ImportBundle:
    deck = DeckCreate(**payload["deck"])
    cards = [CardCreate(deck_id=0, **card) for card in payload["cards"]]
    return ImportBundle(deck=deck, cards=cards)
