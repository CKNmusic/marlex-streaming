from sqlalchemy import Column, Integer, String
from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    host = Column(String, nullable=False)
    recordings_dir = Column(String(512), nullable=False, default="/recordings", server_default="/recordings")
    output_format = Column(String(8), nullable=False, default="mp4", server_default="mp4")
    scan_start_in = Column(Integer, nullable=False, default=60, server_default="60")
