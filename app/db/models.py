from sqlmodel import SQLModel, Field
from datetime import datetime


class ShortURL(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    original_url: str
    short_code: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
