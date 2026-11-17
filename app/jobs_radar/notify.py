"""Admin alerts through the aiogram bot (bot token, never the monitor's user account)."""
import logging

log = logging.getLogger(__name__)


class AdminNotifier:
    def __init__(self, bot, admin_ids) -> None:
        self.bot = bot
        self.admin_ids = list(admin_ids)

    async def alert(self, text: str) -> None:
        """Best-effort: a failed alert must never change monitor state."""
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception:
                log.warning("admin alert was not delivered to %s", admin_id)
