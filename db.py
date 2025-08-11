# db.py
from decimal import Decimal
from datetime import datetime

from sqlalchemy import Column, Integer, BigInteger, Numeric, DateTime, String, func, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declared_attr
from sqlalchemy import select, insert

DATABASE_URL = "sqlite+aiosqlite:///./db.sqlite3"  # файл в проекте

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, nullable=False, unique=True, index=True)  # telegram id

class Money(Base):
    __tablename__ = "money"
    id = Column(Integer, primary_key=True)
    usd_to_rub = Column(Numeric(18, 6), nullable=False)
    usd_to_kz = Column(Numeric(18, 6), nullable=False)
    rub_kz = Column(Numeric(18, 8), nullable=False)
    time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# Async engine + sessionmaker
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Инициализация (создать таблицы)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Добавляет пользователя, если такого нет
async def add_user(tg_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        # сперва проверим есть ли
        result = await session.execute(select(User).where(User.tg_id == int(tg_id)))
        user = result.scalar_one_or_none()
        if user:
            return False
        new = User(tg_id=int(tg_id))
        session.add(new)
        await session.commit()
        return True

# Записать курсы
async def add_money(usd_rub: Decimal, usd_kz: Decimal, rub_kz: Decimal):
    async with AsyncSessionLocal() as session:
        m = Money(
            usd_to_rub=usd_rub,
            usd_to_kz=usd_kz,
            rub_kz=rub_kz
        )
        session.add(m)
        await session.commit()

# Получить последнюю запись
async def get_last_money():
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Money).order_by(Money.time.desc()).limit(1)
        )
        return res.scalar_one_or_none()

# Получить всех пользователей (tg_id list)
async def get_all_user_ids():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User.tg_id))
        return [row[0] for row in res.all()]

