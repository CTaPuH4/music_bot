import logging
from typing import Tuple, Optional, Any
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import settings
from database.db import db

logger = logging.getLogger(__name__)


async def check_user_subscription(
    bot: Bot, user_id: int
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Checks if a user is subscribed to the mandatory Telegram channel.
    Returns:
        (is_subscribed: bool, channel_identifier: Optional[str], channel_url: Optional[str])

    Rules:
    - If subscription check is disabled, returns (True, None, None).
    - If user is an admin (in settings.admin_ids_list), bypasses check: returns (True, None, None).
    - If no channel is configured, logs warning and allows through: returns (True, None, None).
    - Checks Telegram member status: 'creator', 'administrator', 'member' or 'restricted' (if is_member).
    """
    is_enabled = await db.is_subscription_check_enabled()
    if not is_enabled:
        return True, None, None

    # Admins always bypass subscription gate
    if user_id in settings.admin_ids_list:
        return True, None, None

    channel_info = await db.get_required_channel()
    channel = channel_info.get("channel", "").strip()
    channel_url = channel_info.get("url", "").strip()

    if not channel:
        logger.warning("Mandatory subscription check is ON, but no channel is configured!")
        return True, None, None

    try:
        # Support numeric channel ID (e.g. -100123456789) or string username (@channel)
        chat_id_param: Any = channel
        if channel.startswith("-") and channel[1:].isdigit():
            chat_id_param = int(channel)

        member = await bot.get_chat_member(chat_id=chat_id_param, user_id=user_id)

        # Standard Telegram subscribed statuses
        if member.status in ("creator", "administrator", "member"):
            return True, channel, channel_url

        if member.status == "restricted":
            is_member = getattr(member, "is_member", True)
            if is_member:
                return True, channel, channel_url

        return False, channel, channel_url

    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "user not found" in err_msg or "participant_id_invalid" in err_msg:
            # User is definitely not in the channel
            return False, channel, channel_url
        elif "chat not found" in err_msg:
            logger.warning("Mandatory channel %s was not found: %s", channel, e)
            return True, channel, channel_url
        elif "not enough rights" in err_msg or "bot is not a member" in err_msg:
            logger.warning("Bot has insufficient rights in channel %s: %s", channel, e)
            return True, channel, channel_url
        else:
            logger.warning("TelegramBadRequest while checking subscription for user %s: %s", user_id, e)
            return False, channel, channel_url

    except TelegramForbiddenError as e:
        logger.warning("Bot is forbidden in channel %s: %s", channel, e)
        return True, channel, channel_url

    except Exception as e:
        logger.error("Unexpected error in check_user_subscription for user %s: %s", user_id, e)
        return True, channel, channel_url
