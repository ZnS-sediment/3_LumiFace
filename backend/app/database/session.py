from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import DATA, prepare_storage

prepare_storage()
engine = create_engine(
    f"sqlite:///{DATA / 'lumiface.db'}", connect_args={"check_same_thread": False, "timeout": 30}
)


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute("PRAGMA journal_mode=WAL")


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
