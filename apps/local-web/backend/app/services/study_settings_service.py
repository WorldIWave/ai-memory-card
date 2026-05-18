# Input: Session 与 StudySettingsUpdate payload  |  Output: 全局 AppStudySettings 单例记录
# Output: 提供 ensure/get/update，向 review session 和设置页暴露同一套学习限制
# Role: 这是“全局学习设置”从数据库读写到默认值回填的业务层
# Use: 当前固定使用 id=1 单例；改默认值或新增字段时要同步迁移与前端设置页
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.db.models import AppStudySettings
from app.schemas.study_settings import StudySettingsUpdate


class StudySettingsService:
    DEFAULT_DAILY_NEW_LIMIT = 20
    DEFAULT_DAILY_REVIEW_LIMIT = 100
    DEFAULT_SCHEDULER_MODE = "traditional"
    SINGLETON_ID = 1

    def ensure(self, session: Session) -> AppStudySettings:
        settings = session.get(AppStudySettings, self.SINGLETON_ID)
        if settings is not None:
            return settings

        now = datetime.now(timezone.utc)
        settings = AppStudySettings(
            id=self.SINGLETON_ID,
            daily_new_limit=self.DEFAULT_DAILY_NEW_LIMIT,
            daily_review_limit=self.DEFAULT_DAILY_REVIEW_LIMIT,
            scheduler_mode=self.DEFAULT_SCHEDULER_MODE,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            settings = session.get(AppStudySettings, self.SINGLETON_ID)
            if settings is None:
                raise
        session.refresh(settings)
        return settings

    def get(self, session: Session) -> AppStudySettings:
        return self.ensure(session)

    def update(self, session: Session, payload: StudySettingsUpdate) -> AppStudySettings:
        settings = self.ensure(session)
        settings.daily_new_limit = payload.daily_new_limit
        settings.daily_review_limit = payload.daily_review_limit
        if "scheduler_mode" in payload.model_fields_set:
            settings.scheduler_mode = payload.scheduler_mode
        settings.updated_at = datetime.now(timezone.utc)
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings
