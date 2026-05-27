from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_path = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    is_indexed = Column(Boolean, nullable=False, default=False, server_default="0")

    chunks = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
