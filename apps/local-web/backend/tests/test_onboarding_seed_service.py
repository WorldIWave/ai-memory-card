# Input: service-level SQLite session and runtime settings | Output: onboarding seed assertions
# Role: Locks the first-run tutorial deck contract so existing users are not surprised by new seed data
# Note: Seed creation is opt-in by runtime mode or explicit env/config; service itself is idempotent
# Usage: pytest tests/test_onboarding_seed_service.py
from sqlmodel import select

from app.core.config import Settings
from app.db.models import AppSeedState, Card, CardReviewState, Deck, Folder
from app.services.onboarding_seed_service import (
    ONBOARDING_TUTORIAL_SEED_KEY,
    ONBOARDING_TUTORIAL_SEED_VERSION,
    TUTORIAL_DECK_NAME,
    OnboardingSeedService,
    should_enable_onboarding_seed,
)


def test_should_enable_onboarding_seed_uses_runtime_mode_by_default() -> None:
    assert should_enable_onboarding_seed(Settings(runtime_mode="development")) is False
    assert should_enable_onboarding_seed(Settings(runtime_mode="dev")) is True
    assert should_enable_onboarding_seed(Settings(runtime_mode="bundled")) is True


def test_should_enable_onboarding_seed_allows_explicit_override() -> None:
    assert should_enable_onboarding_seed(Settings(runtime_mode="bundled", enable_onboarding_seed=False)) is False
    assert should_enable_onboarding_seed(Settings(runtime_mode="development", enable_onboarding_seed=True)) is True


def test_ensure_creates_tutorial_deck_cards_and_seed_state_for_empty_database(session) -> None:
    created = OnboardingSeedService().ensure(session)

    assert created is True

    seed_state = session.get(AppSeedState, ONBOARDING_TUTORIAL_SEED_KEY)
    assert seed_state is not None
    assert seed_state.seed_version == ONBOARDING_TUTORIAL_SEED_VERSION

    deck = session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).one()
    assert deck.folder_id == 1
    assert deck.source_type == "system_seed"

    cards = session.exec(select(Card).where(Card.deck_id == deck.id)).all()
    assert len(cards) >= 8
    assert {card.card_type for card in cards} == {"recall"}
    assert {card.source_type for card in cards} == {"system_seed"}
    assert all("tutorial" in card.tags for card in cards)
    assert all(session.get(CardReviewState, card.id) is not None for card in cards)


def test_ensure_is_idempotent_after_seed_state_exists(session) -> None:
    service = OnboardingSeedService()

    assert service.ensure(session) is True
    assert service.ensure(session) is False

    decks = session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).all()
    cards = session.exec(select(Card)).all()

    assert len(decks) == 1
    assert len(cards) >= 8


def test_ensure_upgrades_legacy_seed_state_that_marked_existing_users_without_tutorial(session) -> None:
    folder = Folder(id=1, name="默认文件夹")
    deck = Deck(name="Existing deck", folder_id=1)
    session.add(folder)
    session.add(deck)
    session.add(AppSeedState(seed_key=ONBOARDING_TUTORIAL_SEED_KEY, seed_version=1))
    session.commit()

    created = OnboardingSeedService().ensure(session)

    assert created is True
    seed_state = session.get(AppSeedState, ONBOARDING_TUTORIAL_SEED_KEY)
    assert seed_state is not None
    assert seed_state.seed_version == ONBOARDING_TUTORIAL_SEED_VERSION
    assert session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).first() is not None


def test_ensure_does_not_recreate_tutorial_after_user_deletes_it(session) -> None:
    service = OnboardingSeedService()
    assert service.ensure(session) is True

    deck = session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).one()
    for card in session.exec(select(Card).where(Card.deck_id == deck.id)).all():
        state = session.get(CardReviewState, card.id)
        if state is not None:
            session.delete(state)
        session.delete(card)
    session.delete(deck)
    session.commit()

    assert service.ensure(session) is False
    assert session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).first() is None


def test_ensure_adds_tutorial_content_for_existing_database_once(session) -> None:
    folder = Folder(id=1, name="默认文件夹")
    deck = Deck(name="Existing deck", folder_id=1)
    session.add(folder)
    session.add(deck)
    session.commit()

    created = OnboardingSeedService().ensure(session)

    assert created is True
    assert session.get(AppSeedState, ONBOARDING_TUTORIAL_SEED_KEY) is not None
    assert session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).first() is not None
    assert len(session.exec(select(Deck)).all()) == 2


def test_ensure_marks_existing_tutorial_deck_without_duplicating_it(session) -> None:
    folder = Folder(id=1, name="默认文件夹")
    tutorial_deck = Deck(name=TUTORIAL_DECK_NAME, folder_id=1, source_type="manual")
    session.add(folder)
    session.add(tutorial_deck)
    session.commit()

    created = OnboardingSeedService().ensure(session)

    assert created is False
    assert session.get(AppSeedState, ONBOARDING_TUTORIAL_SEED_KEY) is not None
    assert len(session.exec(select(Deck).where(Deck.name == TUTORIAL_DECK_NAME)).all()) == 1
