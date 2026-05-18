# Input: SQLModel Session plus runtime settings | Output: optional first-run tutorial deck and seed-state row
# Role: Owns idempotent onboarding content creation for fresh local databases
# Note: Existing databases are marked as handled without inserting tutorial content; deleted tutorial decks are not recreated
# Usage: Called during backend startup after migrations, and directly by service tests
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.config import Settings
from app.db.models import AppSeedState, Card, CardReviewState, Deck, Folder

ONBOARDING_TUTORIAL_SEED_KEY = "onboarding_tutorial_deck"
ONBOARDING_TUTORIAL_SEED_VERSION = 2
TUTORIAL_DECK_NAME = "快速上手 AI Memory Card"
_SEED_ENABLED_RUNTIME_MODES = {"dev", "bundled"}

_TUTORIAL_CARDS: tuple[tuple[str, str], ...] = (
    (
        "AI Memory Card 是什么？",
        "AI Memory Card 是一款本地优先的记忆卡学习软件，用牌组、卡片和复习记录帮助你长期保存知识。",
    ),
    (
        "为什么主动回忆比反复阅读更有效？",
        "主动回忆会迫使大脑重新提取答案，能更准确地暴露薄弱点，也更容易形成长期记忆。",
    ),
    (
        "牌组在应用里有什么作用？",
        "牌组用于组织同一主题的卡片，也可以作为复习范围，让你专注处理当前要学习的一组知识。",
    ),
    (
        "复习评分 Again、Hard、Good、Easy 分别表示什么？",
        "Again 表示没有想起来，Hard 表示很吃力，Good 表示基本掌握，Easy 表示很轻松。应用会根据评分调整后续出现时间。",
    ),
    (
        "为什么间隔复习适合长期学习？",
        "间隔复习会在快要遗忘时安排再次练习，用更少次数维持更长时间的记忆。",
    ),
    (
        "卡片删除后一定会立刻消失吗？",
        "普通卡片删除会先进入回收站，方便误删后恢复；清空回收站或永久删除才会真正移除。",
    ),
    (
        "数据页可以帮助你观察什么？",
        "数据页汇总最近复习趋势、评分分布和牌组活跃度，帮助你判断学习节奏是否稳定。",
    ),
    (
        "AI 功能在这个应用里扮演什么角色？",
        "AI 是可插拔的辅助能力，可以用于生成卡片、评估理解或解释知识点；没有 AI 时，核心复习流程仍然完整可用。",
    ),
    (
        "如何开始自己的第一组学习卡片？",
        "进入牌库，新建牌组，然后创建问题和答案清晰的卡片。建议每张卡片只考察一个小知识点。",
    ),
    (
        "本地优先意味着什么？",
        "你的学习数据优先保存在本机目录中，软件可以在没有远端服务的情况下继续管理卡片和复习记录。",
    ),
)


def should_enable_onboarding_seed(settings: Settings) -> bool:
    if settings.enable_onboarding_seed is not None:
        return settings.enable_onboarding_seed
    return settings.runtime_mode.lower() in _SEED_ENABLED_RUNTIME_MODES


class OnboardingSeedService:
    def ensure(self, session: Session) -> bool:
        seed_state = session.get(AppSeedState, ONBOARDING_TUTORIAL_SEED_KEY)
        if seed_state is not None and seed_state.seed_version >= ONBOARDING_TUTORIAL_SEED_VERSION:
            return False

        if self._has_existing_tutorial_deck(session):
            self._mark_handled(session, seed_state)
            session.commit()
            return False

        self._ensure_default_folder(session)
        deck = Deck(
            name=TUTORIAL_DECK_NAME,
            description="内置上手教程：介绍 AI 记忆卡、主动回忆和间隔复习。",
            default_scheduler_type="sm2_basic",
            source_type="system_seed",
            folder_id=1,
        )
        session.add(deck)
        session.flush()

        for index, (front, back) in enumerate(_TUTORIAL_CARDS, start=1):
            card = Card(
                deck_id=deck.id,
                card_type="recall",
                front=front,
                back=back,
                tags=["tutorial"],
                render_format="markdown",
                sort_order=index,
                source_type="system_seed",
            )
            session.add(card)
            session.flush()
            if card.id is None:
                raise RuntimeError("Seed card id was not assigned after flush")
            session.add(CardReviewState(card_id=card.id, scheduler_type="sm2_basic"))

        self._mark_handled(session, seed_state)
        session.commit()
        return True

    def _has_existing_tutorial_deck(self, session: Session) -> bool:
        return session.exec(select(Deck.id).where(Deck.name == TUTORIAL_DECK_NAME).limit(1)).first() is not None

    def _ensure_default_folder(self, session: Session) -> None:
        if session.get(Folder, 1) is None:
            session.add(Folder(id=1, name="默认文件夹"))
            session.flush()

    def _mark_handled(self, session: Session, seed_state: AppSeedState | None = None) -> None:
        now = datetime.now(timezone.utc)
        if seed_state is None:
            session.add(
                AppSeedState(
                    seed_key=ONBOARDING_TUTORIAL_SEED_KEY,
                    seed_version=ONBOARDING_TUTORIAL_SEED_VERSION,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            seed_state.seed_version = ONBOARDING_TUTORIAL_SEED_VERSION
            seed_state.updated_at = now
            session.add(seed_state)
