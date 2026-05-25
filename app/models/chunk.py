import json

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = Column(Integer, nullable=False)           # 0-based chunk position in the document
    breadcrumbs = Column(Text, nullable=False)           # JSON-encoded list[str]
    token_count = Column(Integer, nullable=False)
    embedding_model = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)

    document = relationship("Document", back_populates="chunks")

    def get_breadcrumbs(self) -> list[str]:
        return json.loads(self.breadcrumbs)
