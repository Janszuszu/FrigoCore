"""FrigoCore — global key/value application settings editable by an admin.

Used for integration configuration that is entered through the UI rather
than deployment env vars (e.g. the VoIPstudio API key). Secret values are
stored encrypted — see app.core.secret_box.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AppSetting {self.key!r}>"
