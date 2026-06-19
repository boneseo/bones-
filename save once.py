# meta developer: @bmodules
# scope: heroku_only

import os
import tempfile
from datetime import timezone, timedelta

from herokutl import events
from herokutl.types import Message, MessageEntityCustomEmoji
from .. import loader


MSK = timezone(timedelta(hours=3))


@loader.tds
class SaveOnceMod(loader.Module):
    """Модуль для сохранения одноразовых фото/видео"""

    strings = {"name": "SaveOnce"}
    FIRE = "🔥"
    FIRE_LEN = 2

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "autosave",
                False,
                "Автосохранение одноразовых медиа из ЛС",
            )
        )

    def _is_once(self, media) -> bool:
        return hasattr(media, "ttl_seconds") and media.ttl_seconds

    async def _save_media(self, reply, client):
        is_video = hasattr(reply.media, "document")
        ext = ".mp4" if is_video else ".jpg"

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name

        await reply.download_media(tmp_path)

        try:
            sender = await reply.get_sender()
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

        caption = (
            f"{self.FIRE} Сообщение от [{name}]\n"
            f"{self.FIRE} Время [{msg_time} МСК]"
        )

        first_line_len = self.FIRE_LEN + len(f" Сообщение от [{name}]\n".encode("utf-16-le")) // 2

        entities = [
            MessageEntityCustomEmoji(
                offset=0,
                length=self.FIRE_LEN,
                document_id=5253780051471642059,
            ),
            MessageEntityCustomEmoji(
                offset=first_line_len,
                length=self.FIRE_LEN,
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

        if not reply or not hasattr(reply, "media") or not reply.media:
            return

        if not self._is_once(reply.media):
            return

        try:
            await self._save_media(reply, message.client)
        except Exception as e:
            await message.client.send_message("me", f"❌ Ошибка: {e}")

    @loader.command()
    async def nlu(self, message: Message):
        """включить / выключить Автосохранение"""
        self.config["autosave"] = not self.config["autosave"]
        enabled = self.config["autosave"]

        if enabled:
            prefix = f"{self.FIRE} Автосохранение включено\n\n> "
            text = f"{prefix}{self.FIRE} Внимание модуль следит только в личных сообщениях"
            entities = [
                MessageEntityCustomEmoji(
                    offset=0,
                    length=self.FIRE_LEN,
                    document_id=5217769366329789092,
                ),
                MessageEntityCustomEmoji(
                    offset=len(prefix.encode("utf-16-le")) // 2,
                    length=self.FIRE_LEN,
                    document_id=5440660757194744323,
                ),
            ]
        else:
            text = f"{self.FIRE} Автосохранение выключено"
            entities = [
                MessageEntityCustomEmoji(
                    offset=0,
                    length=self.FIRE_LEN,
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

    @loader.raw_handler(events.NewMessage)
    async def watcher(self, message: Message):
        if not self.config["autosave"]:
            return

        if not getattr(message, "is_private", False):
            return

        if not hasattr(message, "media") or not message.media:
            return

        if not self._is_once(message.media):
            return

        try:
            await self._save_media(message, message.client)
        except Exception:
            pass
