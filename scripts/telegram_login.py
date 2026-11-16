"""Create a Telethon StringSession for the Jobs Source Radar monitor account.

Run it yourself in your own terminal (NOT through an AI assistant, CI or any logged shell):
the printed string is full access to the Telegram account.

    python scripts/telegram_login.py

Uses TG_API_ID / TG_API_HASH from the environment or .env (asks for them if missing), then asks for the
phone, the login code and the 2FA password. The session string is printed to the console once and is never
written to a file or a log: store it as the TG_SESSION secret (e.g. in the Render dashboard).
"""
import asyncio
import getpass
import os
import sys

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def ask(prompt: str, secret: bool = False) -> str:
    return (await asyncio.to_thread(getpass.getpass if secret else input, prompt)).strip()


def _api_credentials() -> tuple[int | None, str | None]:
    try:
        from app.config import get_settings

        settings = get_settings()
        return settings.tg_api_id, settings.tg_api_hash
    except Exception:  # settings need BOT_TOKEN; the login does not
        return None, None


async def login_with_code(client: TelegramClient) -> None:
    phone = (await ask("Phone (international format, e.g. +380...): ")).replace(" ", "")
    try:
        sent = await client.send_code_request(phone)
    except errors.FloodWaitError as e:
        raise SystemExit(f"Telegram asks to wait {e.seconds} s before sending a new code.") from None
    except (errors.PhoneNumberInvalidError, errors.PhoneNumberBannedError, errors.ApiIdInvalidError) as e:
        raise SystemExit(f"Cannot send the login code: {type(e).__name__}") from None
    code = await ask("Login code: ")
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except errors.SessionPasswordNeededError:
        await client.sign_in(password=await ask("2FA password: ", secret=True))
    except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError) as e:
        raise SystemExit(f"Login code rejected ({type(e).__name__}). Run again.") from None


async def main() -> None:
    api_id, api_hash = _api_credentials()
    if api_id is None:
        api_id = int(await ask("TG_API_ID (my.telegram.org): "))
    if not api_hash:
        api_hash = await ask("TG_API_HASH: ", secret=True)

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        await login_with_code(client)
        me = await client.get_me()
        session = client.session.save()
    finally:
        await client.disconnect()

    print(f"\nLogged in as {me.first_name} (id {me.id}).")
    print("WARNING: the string below is full access to this account. Store it only as the TG_SESSION")
    print("secret. It is shown once, is not saved anywhere, and must never be committed or pasted into chats.\n")
    print(session)
    print()


if __name__ == "__main__":
    asyncio.run(main())
