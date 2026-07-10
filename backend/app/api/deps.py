from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.lifecycle import market_allows_mutations
from app.core.roles import MarketRole
from app.core.security import decode_access_token, decode_platform_access_token
from app.models import MarketUser, PlatformAdmin, User


bearer_scheme = HTTPBearer(auto_error=False)


async def _no_session_dependency() -> None:
    return None


OptionalSession = Annotated[AsyncSession | None, Depends(_no_session_dependency)]


class DeferredCatalogSession:
    def __init__(self, session_dependency):
        self._session_dependency = session_dependency
        self._session_iterator = None
        self._session: AsyncSession | None = None

    async def get(self) -> AsyncSession:
        if self._session is None:
            self._session_iterator = self._session_dependency()
            self._session = await anext(self._session_iterator)
        return self._session

    async def close(self) -> None:
        if self._session_iterator is not None:
            await self._session_iterator.aclose()
            self._session_iterator = None
            self._session = None


async def get_catalog_session() -> AsyncGenerator[AsyncSession, None]:
    try:
        async for session in get_session():
            yield session
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        ) from exc


async def get_deferred_catalog_session(request: Request) -> AsyncGenerator[DeferredCatalogSession, None]:
    session_dependency = request.app.dependency_overrides.get(get_catalog_session, get_catalog_session)
    deferred_session = DeferredCatalogSession(session_dependency)
    try:
        yield deferred_session
    finally:
        await deferred_session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
    session: OptionalSession = None,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum gerekli.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz oturum.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz oturum.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    active_session = session if session is not None else await deferred_session.get()
    user = await active_session.scalar(
        select(User)
        .options(selectinload(User.market_memberships).selectinload(MarketUser.market))
        .where(User.id == user_uuid, User.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz oturum.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_platform_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
    session: OptionalSession = None,
) -> PlatformAdmin:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Platform oturumu gerekli.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_platform_access_token(credentials.credentials)
    admin_id = payload.get("sub")
    if not isinstance(admin_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz platform oturumu.")
    try:
        admin_uuid = UUID(admin_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz platform oturumu.") from None
    active_session = session if session is not None else await deferred_session.get()
    admin = await active_session.scalar(
        select(PlatformAdmin).where(PlatformAdmin.id == admin_uuid, PlatformAdmin.is_active.is_(True))
    )
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz platform oturumu.")
    return admin


async def get_current_market_membership(
    x_market_id: UUID | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
    session: OptionalSession = None,
) -> MarketUser:
    if x_market_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Market-Id seçili market için gereklidir.",
        )
    statement = (
        select(MarketUser)
        .options(selectinload(MarketUser.market))
        .where(
            MarketUser.market_id == x_market_id,
            MarketUser.user_id == current_user.id,
            MarketUser.is_active.is_(True),
        )
    )
    active_session = session if session is not None else await deferred_session.get()
    membership = await active_session.scalar(statement)
    if membership is None or membership.market is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu market için yetkiniz yok.",
        )
    lifecycle_status = membership.market.lifecycle_status or "active"
    if lifecycle_status == "archived":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu market arşivlenmiş.")
    if not membership.market.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu market için yetkiniz yok.",
        )
    if lifecycle_status not in {"trial", "active"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu market su anda kullanima kapali.")
    return membership


async def require_market_member(
    x_market_id: UUID | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
    session: OptionalSession = None,
) -> UUID:
    membership = await get_current_market_membership(x_market_id, current_user, deferred_session, session)
    return membership.market_id


async def get_current_market_id(market_id: UUID = Depends(require_market_member)) -> UUID:
    return market_id


async def get_required_market_id(market_id: UUID = Depends(require_market_member)) -> UUID:
    return market_id


def require_market_roles(*allowed_roles: str | MarketRole):
    role_values = tuple(role.value if isinstance(role, MarketRole) else role for role in allowed_roles)

    async def dependency(
        membership: MarketUser = Depends(get_current_market_membership),
    ) -> MarketUser:
        if membership.role not in role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için yetkiniz bulunmuyor.",
            )
        if not market_allows_mutations(membership.market):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu markette değişiklik işlemleri geçici olarak durduruldu.",
            )
        return membership

    return dependency


def require_market_role(*allowed_roles: str | MarketRole):
    async def dependency(membership: MarketUser = Depends(require_market_roles(*allowed_roles))) -> UUID:
        return membership.market_id

    return dependency


require_market_admin = require_market_roles(MarketRole.MARKET_ADMIN)


async def get_campaign_session(
    market_id: UUID = Depends(get_required_market_id),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
) -> AsyncGenerator[AsyncSession, None]:
    _ = market_id
    yield await deferred_session.get()
