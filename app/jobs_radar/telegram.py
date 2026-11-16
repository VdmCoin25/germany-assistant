"""Thin Telethon wrappers for joining. Read-only account: only join and lookup requests live here."""
from telethon import TelegramClient, utils
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import ChatInviteAlready
from telethon.tl.types.messages import ChatInviteJoinResultOk

from app.jobs_radar.tglinks import ChatLink


async def join_chat(client: TelegramClient, link: ChatLink) -> int:
    """Join and return the marked chat id. May raise Telethon RPC errors."""
    if link.kind == "username":
        entity = await client.get_entity(link.value)
        await client(JoinChannelRequest(entity))
        return utils.get_peer_id(entity)
    result = await client(ImportChatInviteRequest(link.value))
    # Older layers return Updates; newer ones messages.ChatInviteJoinResultOk(updates=Updates).
    updates = result.updates if isinstance(result, ChatInviteJoinResultOk) else result
    chats = getattr(updates, "chats", None)
    if chats:
        return utils.get_peer_id(chats[0])
    chat_id = await check_membership(client, link)
    if chat_id is None:
        raise RuntimeError(f"joined via invite but chat id not resolvable ({type(result).__name__})")
    return chat_id


async def check_membership(client: TelegramClient, link: ChatLink) -> int | None:
    """Marked chat id if we are already a member, else None. Read-only lookups."""
    if link.kind == "invite":
        info = await client(CheckChatInviteRequest(link.value))
        return utils.get_peer_id(info.chat) if isinstance(info, ChatInviteAlready) else None
    entity = await client.get_entity(link.value)
    try:
        await client.get_permissions(entity, "me")
    except UserNotParticipantError:
        return None
    return utils.get_peer_id(entity)
