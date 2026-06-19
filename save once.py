# meta developer: @bmodules
# scope: heroku_only

import logging
import os
import tempfile
from datetime import timezone, timedelta

from herokutl import events
from herokutl.types import Message, MessageEntityCustomEmoji
from .. import loader

logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))

FIRE = "🔥"
FIRE_LEN = len(FIRE.encode("utf-16-le")) // 2

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


@loader.tds
class SaveOnceMod(loader.Module):
    """Модуль для сохранения одноразовых фото/видео"""

    strings = {"name": "SaveOnce"}

    def __init__(self):
        super().__init__()
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "autosave",
                False,
                "Автосохранение одноразовых медиа из ЛС",
            )
        )

    async def _save_media(self, reply, client):
        mime = getattr(getattr(reply.media, "document", None), "mime_type", "image/jpeg")
        ext = MIME_TO_EXT.get(mime, ".jpg")

        tmp_path = os.path.join(tempfile.gettempdir(), f"saveonce_{reply.id}{ext}")
        await reply.download_media(tmp_path)

        try:
            sender = reply.sender or await reply.get_sender()
            if sender:
                name = (
                    f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                    or sender.username
                    or str(sender.id)
                )
            else:
                name = str(reply.sender_id)
        except Exception:
            name = str(reply.sender_id)

        msg_time = reply.date.astimezone(MSK).strftime("%d.%m.%Y %H:%M")

        first_line = f"{FIRE} Сообщение от [{name}]\n"
        caption = f"{first_line}{FIRE} Время [{msg_time} МСК]"
        first_line_len = len(first_line.encode("utf-16-le")) // 2

        entities = [
            MessageEntityCustomEmoji(
                offset=0,
                length=FIRE_LEN,
                document_id=5253780051471642059,
            ),
            MessageEntityCustomEmoji(
                offset=first_line_len,
                length=FIRE_LEN,
                document_id=5255772095958229697,
            ),
        ]

        await client.send_file(
            "me",
            tmp_path,
            caption=caption,
            formatting_entities=entities,
            force_document=False,
        )

        os.remove(tmp_path)

    @loader.command()
    async def nn(self, message: Message):
        """сохраняет одноразовое фото ответом на фото"""
        reply = await message.get_reply_message()

        await message.delete()

        if not reply or not reply.media:
            return

        if not getattr(reply.media, "ttl_seconds", None):
            return

        try:
            await self._save_media(reply, message.client)
        except Exception as e:
            await message.client.send_message("me", f"❌ Ошибка: {e}")

    @loader.command()
    async def nlu(self, message: Message):
        """включить / выключить Автосохранение"""
        self.config["autosave"] = not self.config["autosave"]

        if self.config["autosave"]:
            prefix = f"{FIRE} Автосохранение включено\n\n> "
            text = f"{prefix}{FIRE} Внимание модуль следит только в личных сообщениях"
            prefix_len = len(prefix.encode("utf-16-le")) // 2
            entities = [
                MessageEntityCustomEmoji(
                    offset=0,
                    length=FIRE_LEN,
                    document_id=5217769366329789092,
                ),
                MessageEntityCustomEmoji(
                    offset=prefix_len,
                    length=FIRE_LEN,
                    document_id=5440660757194744323,
                ),
            ]
        else:
            text = f"{FIRE} Автосохранение выключено"
            entities = [
                MessageEntityCustomEmoji(
                    offset=0,
                    length=FIRE_LEN,
                    document_id=5217769366329789092,
                ),
            ]

        await message.client.send_message(
            message.peer_id,
            text,
            formatting_entities=entities,
            reply_to=message.id,
        )
        await message.delete()

    @loader.raw_handler(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def watcher(self, message: Message):
        if not self.config["autosave"]:
            return

        if not message.media:
            return

        if not getattr(message.media, "ttl_seconds", None):
            return

        try:
            await self._save_media(message, message.client)
        except Exception:
            logger.exception("SaveOnce watcher: не удалось сохранить медиа")
