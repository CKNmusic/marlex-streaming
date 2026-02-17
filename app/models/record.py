import hashlib
import json
import os
import re

from sqlalchemy import BigInteger, Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="SET NULL"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    place_id = Column(Integer, ForeignKey("places.id", ondelete="RESTRICT"), nullable=False)
    
    # Metadata
    title = Column(String, nullable=True) # Optional, default logic in service
    description = Column(Text, nullable=True) # Optional
    
    # Timestamps
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    seq = Column(Integer, nullable=True)

    # Lifecycle logs
    output_path = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    final_status = Column(String, nullable=True)
    stop_reason = Column(String, nullable=True)
    lifecycle_log = Column(Text, nullable=True)
    
    # Relations
    owner = relationship("User", back_populates="records")
    device = relationship("Device", back_populates="records")
    procedure = relationship("Procedure", back_populates="records")
    place = relationship("Place", back_populates="records")

    def _lifecycle_payload(self) -> dict:
        raw = str(self.lifecycle_log or "").strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @property
    def file_key(self) -> str | None:
        if not self.output_path:
            return None
        normalized = os.path.normpath(str(self.output_path))
        parts = [item for item in normalized.split(os.sep) if item]
        if len(parts) >= 3:
            candidate = parts[-3]
            if re.fullmatch(r"[A-Za-z0-9]{4,64}", candidate):
                return candidate.upper()

        filename = os.path.basename(normalized)
        matched = re.match(r"^\d{8}([A-Za-z0-9]{4,64})(?:_\d+)?\.(?:mp4|mkv)$", filename, re.IGNORECASE)
        if matched:
            return matched.group(1).upper()
        return None

    @property
    def public_id(self) -> str:
        file_key = self.file_key
        if file_key:
            return file_key
        seed = f"{self.owner_id}:{self.device_id}:{self.seq or 0}:{self.id}"
        digest = hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
        return f"REC-{digest}"

    @property
    def video_resolution(self) -> str | None:
        value = self._lifecycle_payload().get("video_resolution")
        normalized = str(value or "").strip()
        return normalized or None

    @property
    def video_codec(self) -> str | None:
        value = self._lifecycle_payload().get("video_codec")
        normalized = str(value or "").strip()
        return normalized or None

    @property
    def audio_codec(self) -> str | None:
        value = self._lifecycle_payload().get("audio_codec")
        normalized = str(value or "").strip()
        return normalized or None
