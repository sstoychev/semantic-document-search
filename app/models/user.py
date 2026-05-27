from sqlalchemy import Column, Integer, String

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    permissions = Column(Integer, nullable=False, default=1)  # bitmask; see app/permissions.py
    jwt_salt = Column(String, nullable=False)  # JWT secret = password_hash + jwt_salt
