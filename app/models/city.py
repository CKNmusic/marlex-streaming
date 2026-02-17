from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.db.base import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    uf = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

    places = relationship("Place", back_populates="city")
