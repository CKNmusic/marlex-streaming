import hashlib
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    select,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import column_property, relationship, synonym

from app.db.base import Base
from app.models.mark import Mark
from app.models.protocol import Protocol
from app.services.device_status import DEVICE_STATUS_OFFLINE, DEVICE_STATUS_VALUES


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("sn", "mark_id", name="uq_devices_sn_mark"),
    )

    id = Column(Integer, primary_key=True, index=True)
    model = Column(String, index=True, nullable=False)  # "Modelo" do dispositivo
    # Alias temporario para compatibilidade com payloads/fluxos antigos.
    name = synonym("model")
    sn = Column(String, nullable=False, index=True)
    key = Column(String, nullable=True, unique=True, index=True) # hash(id + sn)
    mark_id = Column(Integer, ForeignKey("marks.id", ondelete="RESTRICT"), nullable=False, index=True)
    place_id = Column(Integer, ForeignKey("places.id", ondelete="RESTRICT"), nullable=False)
    protocol_id = Column(Integer, ForeignKey("protocols.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_active = Column(Boolean, default=True)

    status = Column(
        Enum(*DEVICE_STATUS_VALUES, name="device_status"),
        nullable=False,
        default=DEVICE_STATUS_OFFLINE,
        server_default=DEVICE_STATUS_OFFLINE,
    )
    last_seen = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Read-only protocol name projected from FK for API compatibility.
    protocol = column_property(
        select(Protocol.name)
        .where(Protocol.id == protocol_id)
        .correlate_except(Protocol)
        .scalar_subquery()
    )
    mark_name = column_property(
        select(Mark.name)
        .where(Mark.id == mark_id)
        .correlate_except(Mark)
        .scalar_subquery()
    )
    
    # Relationships
    records = relationship("Record", back_populates="device")
    user_access = relationship("UserDeviceAccess", back_populates="device", cascade="all,delete-orphan")
    place = relationship("Place", back_populates="devices")
    active_protocol = relationship("Protocol")
    mark = relationship("Mark", back_populates="devices")

    def generate_key(self):
        """Generates equipment key: hash(id + sn)"""
        if not self.key and self.id and self.sn:
            content = f"{self.id}{self.sn}"
            # MD5 hex (32 chars) -> take first 12 as "smallest possible"
            self.key = hashlib.md5(content.encode()).hexdigest()[:12]


@event.listens_for(Device, "after_insert")
def receive_after_insert(mapper, connection, target):
    # Guarantees key generation even when Device is created outside API flows.
    if target.key or not target.id or not target.sn:
        return
    content = f"{target.id}{target.sn}"
    key = hashlib.md5(content.encode()).hexdigest()[:12]
    connection.execute(
        Device.__table__.update()
        .where(Device.__table__.c.id == target.id)
        .values(key=key)
    )
    target.key = key


@event.listens_for(Device, "before_insert")
def receive_before_insert(mapper, connection, target):
    if getattr(target, "mark_id", None) is None:
        marks_table = Mark.__table__
        default_mark_id = connection.execute(
            select(marks_table.c.id)
            .where(func.lower(marks_table.c.name) == "generic")
            .order_by(marks_table.c.id)
            .limit(1)
        ).scalar()
        if default_mark_id is None:
            default_mark_id = connection.execute(
                marks_table.insert()
                .values(name="Generic", is_active=True)
                .returning(marks_table.c.id)
            ).scalar()
        if default_mark_id is not None:
            target.mark_id = int(default_mark_id)

    # Guarantee a protocol mapping even when fixtures/scripts omit protocol_id.
    if getattr(target, "protocol_id", None) is not None:
        return
    protocols_table = Protocol.__table__
    default_protocol_id = connection.execute(
        select(protocols_table.c.id)
        .where(func.lower(protocols_table.c.name) == "srt")
        .order_by(protocols_table.c.id)
        .limit(1)
    ).scalar()
    if default_protocol_id is None:
        default_protocol_id = connection.execute(
            protocols_table.insert()
            .values(name="srt", port=9000, is_active=True)
            .returning(protocols_table.c.id)
        ).scalar()
    if default_protocol_id is not None:
        target.protocol_id = int(default_protocol_id)

@event.listens_for(Device, "before_update")
def receive_before_update(mapper, connection, target):
    # Key is immutable
    pass
