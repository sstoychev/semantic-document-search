from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, db: Session, payload: UserCreate) -> User:
        """
        Persist a new user.
        TODO: hash password with passlib before storing.
        """
        db_user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=payload.password,  # TODO: replace with hashed value
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def get(self, db: Session, user_id: int) -> User | None:
        """Retrieve a single user by primary key."""
        return db.query(User).filter(User.id == user_id).first()

    def get_by_username(self, db: Session, username: str) -> User | None:
        """Retrieve a user by username."""
        return db.query(User).filter(User.username == username).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        """Retrieve a user by email."""
        return db.query(User).filter(User.email == email).first()

    def get_many(self, db: Session, skip: int = 0, limit: int = 100) -> list[User]:
        """Return a paginated list of users."""
        return db.query(User).offset(skip).limit(limit).all()

    def update(self, db: Session, user_id: int, payload: UserUpdate) -> User | None:
        """
        Update user fields.
        TODO: hash new password if provided.
        """
        db_user = self.get(db, user_id)
        if db_user is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(db_user, field, value)
        db.commit()
        db.refresh(db_user)
        return db_user

    def delete(self, db: Session, user_id: int) -> bool:
        """Remove a user."""
        db_user = self.get(db, user_id)
        if db_user is None:
            return False
        db.delete(db_user)
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def authenticate(self, db: Session, username: str, password: str) -> User | None:
        """
        Verify credentials and return the user if valid.
        TODO: verify password against stored hash using passlib.
        """
        user = self.get_by_username(db, username)
        if user is None:
            return None
        # TODO: replace with: if not pwd_context.verify(password, user.hashed_password): return None
        return user


user_service = UserService()
