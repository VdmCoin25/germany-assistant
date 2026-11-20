"""Create a Telethon StringSession for the Jobs Source Radar monitor account.

Run it yourself in your own terminal (NOT through an AI assistant, CI or any logged shell):
the printed string is full access to the Telegram account.

    pip install -r requirements-dev.txt     # once, installs qrcode for the QR login
    python scripts/telegram_login.py

Uses TG_API_ID / TG_API_HASH from the environment or .env (asks for them if missing), then offers two ways
to log in: [1] a QR code scanned from the phone app (recommended, no login code needed) or [2] a login code
sent by Telegram (with resend) plus the 2FA password if the account has one. The session string is printed
to the console once as a TG_SESSION=<session> line and is never written to a file or a log: store it only
as the TG_SESSION secret (e.g. in the Render dashboard or a local .env).
"""
import asyncio
import getpass
import os
import sys

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Where Telegram says it delivered the login code.
CODE_DELIVERY = {
    types.auth.SentCodeTypeApp: (
        "in the Telegram app: open Telegram on a device where this account is already "
        "logged in and look for a message from the official 'Telegram' account"
    ),
    types.auth.SentCodeTypeSms: "by SMS",
    types.auth.SentCodeTypeCall: "by a phone call (the code is dictated)",
    types.auth.SentCodeTypeFlashCall: "by a flash call (the code is the caller's last digits)",
    types.auth.SentCodeTypeMissedCall: "by a missed call (the code is the caller's last digits)",
    types.auth.SentCodeTypeEmailCode: "to the login email linked to this account",
    types.auth.SentCodeTypeFragmentSms: "via Fragment (fragment.com, anonymous number)",
}

SEND_CODE_ERRORS = {
    errors.PhoneNumberInvalidError: "Invalid phone number. Use +<country><number>.",
    errors.PhoneNumberBannedError: "This phone number is banned by Telegram.",
    errors.PhoneNumberFloodError: "Too many login attempts for this number. Wait a few hours.",
    errors.ApiIdInvalidError: "TG_API_ID / TG_API_HASH are wrong. Check my.telegram.org.",
}


def describe(sent_type: object) -> str:
    for cls, text in CODE_DELIVERY.items():
        if isinstance(sent_type, cls):
            return text
    return f"via {type(sent_type).__name__}"


async def ask(prompt: str, secret: bool = False) -> str:
    return (await asyncio.to_thread(getpass.getpass if secret else input, prompt)).strip()


def _api_credentials() -> tuple[int | None, str | None]:
    try:
        from app.config import get_settings

        settings = get_settings()
        return settings.tg_api_id, settings.tg_api_hash
    except Exception:  # settings need BOT_TOKEN; the login does not
        return None, None


async def send_code(client: TelegramClient, phone: str, force_sms: bool = False):
    try:
        return await client.send_code_request(phone, force_sms=force_sms)
    except errors.FloodWaitError as e:
        raise SystemExit(f"Telegram asks to wait {e.seconds} s before sending a new code.") from None
    except tuple(SEND_CODE_ERRORS) as e:
        raise SystemExit(SEND_CODE_ERRORS[type(e)]) from None


async def login_with_code(client: TelegramClient) -> None:
    phone = (await ask("Phone (international format, e.g. +380...): ")).replace(" ", "")
    sent = await send_code(client, phone)
    print(f"\nTelegram sent the code {describe(sent.type)}.")
    if sent.next_type is not None:
        print(f"If it doesn't arrive, press Enter to request it {describe(sent.next_type)}.")

    while not (code := await ask("Login code (or Enter to resend): ")):
        sent = await send_code(client, phone, force_sms=True)
        print(f"Code re-sent {describe(sent.type)}.")

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except errors.SessionPasswordNeededError:
        await client.sign_in(password=await ask("2FA password: ", secret=True))
    except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError) as e:
        raise SystemExit(f"Login code rejected ({type(e).__name__}). Run again.") from None


async def login_with_qr(client: TelegramClient) -> None:
    """Like Telegram Desktop: scan a QR in the phone app, no login code needed."""
    try:
        import qrcode  # dev dependency, only needed here
    except ImportError:
        raise SystemExit("The QR login needs the qrcode package: pip install -r requirements-dev.txt") from None

    qr_login = await client.qr_login()
    print(
        "\nOn the phone with this account: Telegram -> Settings -> Devices -> Link Desktop Device,"
        "\nthen scan the QR below. It refreshes every ~30 s until scanned.\n"
    )
    while True:
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_login.url)
        qr.print_ascii(invert=True)
        try:
            await qr_login.wait(timeout=30)
            return
        except (TimeoutError, asyncio.TimeoutError):
            await qr_login.recreate()
        except errors.SessionPasswordNeededError:
            await client.sign_in(password=await ask("2FA password: ", secret=True))
            return


async def main() -> None:
    try:  # Windows consoles (cp1251) cannot print the QR block characters otherwise
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    api_id, api_hash = _api_credentials()
    if api_id is None:
        api_id = int(await ask("TG_API_ID (my.telegram.org): "))
    if not api_hash:
        api_hash = await ask("TG_API_HASH: ", secret=True)

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        mode = await ask("Login by [1] QR code (recommended) or [2] login code? [1]: ")
        if mode == "2":
            await login_with_code(client)
        else:
            await login_with_qr(client)
        me = await client.get_me()
        session = client.session.save()
    finally:
        await client.disconnect()

    print(f"\nLogged in as {me.first_name} (@{me.username or '-'}, id {me.id})")
    print("WARNING: the line below is full access to this account. Store it only as the TG_SESSION")
    print("secret. It is shown once, is not saved anywhere, and must never be committed or pasted into chats.\n")
    print(f"TG_SESSION={session}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
