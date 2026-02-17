from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import synonym
from app.db.base import Base

class Protocol(Base):
    __tablename__ = "protocols"
    id = Column(Integer, primary_key=True, index=True)
    # Physical column uses `name`; `protocol` is kept as ORM alias for API compatibility.
    name = Column(String, unique=True, nullable=False)  # e.g., "rtmp"
    protocol = synonym("name")
    port = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
