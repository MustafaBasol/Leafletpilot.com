from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import AsyncSessionLocal
from app.models import TelegramAccount, User
from app.models.base import utc_now


async def main() -> int:
    parser = argparse.ArgumentParser(description="Link an existing LeafletPilot user to a Telegram user ID.")
    parser.add_argument("--email", required=True, help="Existing LeafletPilot user email.")
    parser.add_argument("--telegram-user-id", required=True, type=int, help="Telegram numeric user ID.")
    parser.add_argument("--username", default=None, help="Optional Telegram username.")
    parser.add_argument("--first-name", default=None, help="Optional Telegram first name.")
    parser.add_argument("--last-name", default=None, help="Optional Telegram last name.")
    args = parser.parse_args()

    if AsyncSessionLocal is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == args.email))
        if user is None:
            print("No existing LeafletPilot user found for that email.", file=sys.stderr)
            return 1

        existing_for_telegram = await session.scalar(
            select(TelegramAccount).where(TelegramAccount.telegram_user_id == args.telegram_user_id)
        )
        if existing_for_telegram is not None and existing_for_telegram.user_id != user.id:
            print("That Telegram user ID is already linked to another LeafletPilot user.", file=sys.stderr)
            return 3

        existing_for_user = await session.scalar(
            select(TelegramAccount).where(TelegramAccount.user_id == user.id, TelegramAccount.is_active.is_(True))
        )
        account = existing_for_telegram or existing_for_user
        if account is None:
            account = TelegramAccount(user_id=user.id, telegram_user_id=args.telegram_user_id)
            session.add(account)
        else:
            account.telegram_user_id = args.telegram_user_id
            account.is_active = True
            account.linked_at = utc_now()
        account.username = args.username
        account.first_name = args.first_name
        account.last_name = args.last_name

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            print("Telegram account link conflicts with existing data.", file=sys.stderr)
            return 3

    print("Telegram account link saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
