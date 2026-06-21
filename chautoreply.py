# meta developer: @bmodules & @mead0wssMods
# scope: heroku_only

import asyncio

from herokutl import functions, types, utils
from herokutl.types import Message

from .. import loader


DEFAULT_REPLY_TEXT = "🔥 Новый пост!"
PREMIUM_EMOJI_ID = 5256079005731271025
ERROR_EMOJI_ID = 5253526631221307799
TOGGLE_EMOJI_ID = 5370905394476516106


@loader.tds
class ChAutoReplyMod(loader.Module):
    """Автоответ под новыми постами в выбранных каналах"""

    strings = {"name": "ChAutoReply"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("enabled", True, "Включён ли автоответ под постами"),
            loader.ConfigValue("delay_seconds", 0, "Задержка перед отправкой автоответа в секундах"),
        )

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.channels = db.get("ChAutoReply", "channels", {})
        self.waiting_for_text = {}

    def _save_channels(self):
        self.db.set("ChAutoReply", "channels", self.channels)

    @staticmethod
    def _u16(text: str) -> int:
        return len(text.encode("utf-16-le")) // 2

    def _emoji(self, emoji_id: int, offset: int = 0):
        return [types.MessageEntityCustomEmoji(offset=offset, length=2, document_id=emoji_id)]

    async def _resolve_channel(self, raw: str):
        raw = raw.strip().removeprefix("https://t.me/").removeprefix("t.me/").lstrip("@")
        return await self.client.get_entity(int(raw) if raw.lstrip("-").isdigit() else raw)

    @loader.command()
    async def ch(self, message: Message):
        """добавить канал для автоответа: .ch t.me/username или .ch id"""
        args = message.raw_text.split(maxsplit=1)
        if len(args) < 2:
            await self.client.send_message(message.peer_id, "💔Укажи ссылку или ID канала!", reply_to=message.id, formatting_entities=self._emoji(ERROR_EMOJI_ID))
            await message.delete()
            return

        link = args[1].strip()

        try:
            entity = await self._resolve_channel(link)
            if not isinstance(entity, types.Channel) or not entity.broadcast:
                raise ValueError
        except Exception:
            await self.client.send_message(message.peer_id, f"💔{link} — не канал!", reply_to=message.id, formatting_entities=self._emoji(ERROR_EMOJI_ID))
            await message.delete()
            return

        marked_id = utils.get_peer_id(entity)  # marked id совпадает с message.chat_id у постов
        link_text = f"t.me/{entity.username}" if entity.username else link

        self.channels[str(marked_id)] = {
            "raw_id": entity.id,
            "link": link_text,
            "reply_text": DEFAULT_REPLY_TEXT,
        }
        self._save_channels()

        line1 = f"🔥 {entity.id} {link_text}\n"
        line2 = "Телеграм канал добавлен в вашу конфигурацию"

        await self.client.send_message(
            message.peer_id,
            line1 + line2,
            reply_to=message.id,
            formatting_entities=self._emoji(PREMIUM_EMOJI_ID) + [
                types.MessageEntityCode(offset=self._u16("🔥 "), length=self._u16(str(entity.id))),
                types.MessageEntityBold(offset=self._u16(line1), length=self._u16(line2)),
            ],
        )
        await message.delete()

    @loader.command()
    async def che(self, message: Message):
        """включить / выключить автоответ под постами"""
        self.config["enabled"] = not self.config["enabled"]
        status = "включен ! \n\n:)" if self.config["enabled"] else "выключен ! \n\n:("
        await self.client.send_message(
            message.peer_id, f"🔥 Автоответ под постами {status}",
            reply_to=message.id, formatting_entities=self._emoji(TOGGLE_EMOJI_ID),
        )
        await message.delete()

    @loader.command()
    async def chs(self, message: Message):
        """задержка перед автоответом в секундах: .chs 3"""
        args = message.raw_text.split(maxsplit=1)
        if len(args) < 2 or not args[1].strip().isdigit():
            await self.client.send_message(message.peer_id, "💔Укажи число секунд! Пример: .chs 3", reply_to=message.id, formatting_entities=self._emoji(ERROR_EMOJI_ID))
            await message.delete()
            return

        seconds = int(args[1].strip())
        self.config["delay_seconds"] = seconds
        await self.client.send_message(
            message.peer_id, f"🔥 Задержка автоответа установлена: {seconds} сек.",
            reply_to=message.id, formatting_entities=self._emoji(PREMIUM_EMOJI_ID),
        )
        await message.delete()

    @loader.command()
    async def chan(self, message: Message):
        """список каналов под автоответом"""
        if not self.channels:
            await self.client.send_message(message.peer_id, "💔Список каналов пуст!", reply_to=message.id, formatting_entities=self._emoji(ERROR_EMOJI_ID))
            await message.delete()
            return

        text_parts = []
        entities = []
        offset = 0

        for channel_id, data in self.channels.items():
            entities.append(types.MessageEntityCustomEmoji(offset=offset, length=2, document_id=PREMIUM_EMOJI_ID))
            line = f"🔥{data.get('raw_id', channel_id)} {data.get('link', channel_id)}\n"
            text_parts.append(line)
            offset += self._u16(line)

        text = "".join(text_parts).rstrip()
        entities.append(types.MessageEntityBlockquote(offset=0, length=self._u16(text), collapsed=True))

        await self.client.send_message(message.peer_id, text, reply_to=message.id, formatting_entities=entities)
        await message.delete()

    def _channels_markup(self):
        return [[{"text": d.get("link", cid), "callback": self._cb_select_channel, "args": (cid,), "style": "primary"}] for cid, d in self.channels.items()]

    @loader.command()
    async def cnell(self, message: Message):
        """inline-меню для редактирования текста автоответа по каналам"""
        if not self.channels:
            await self.client.send_message(message.peer_id, "💔Список каналов пуст!", reply_to=message.id, formatting_entities=self._emoji(ERROR_EMOJI_ID))
            await message.delete()
            return

        await self.inline.form(
            text="Выбери канал, чтобы изменить текст автоответа",
            reply_markup=self._channels_markup(),
            message=message,
        )
        await message.delete()

    async def _cb_select_channel(self, call, channel_id: str):
        data = self.channels.get(channel_id)
        if not data:
            await call.answer("Канал не найден", show_alert=True)
            return

        self.waiting_for_text[call.from_user.id] = (channel_id, call)
        await call.edit(
            f"🌒 Я жду жду :) \n\nнапишите свой текст для телеграм канал {{{data.get('link', channel_id)}}} {{{channel_id}}}",
            reply_markup=[[{"text": "⬅️ Назад", "callback": self._cb_back, "style": "danger"}]],
        )

    async def _cb_back(self, call):
        self.waiting_for_text.pop(call.from_user.id, None)
        await call.edit("Выбери канал, чтобы изменить текст автоответа", reply_markup=self._channels_markup())

    async def _handle_text_input(self, message: Message):
        if not message.is_private:
            return

        if message.sender_id not in self.waiting_for_text:
            return

        channel_id, saved_call = self.waiting_for_text.pop(message.sender_id)

        if channel_id not in self.channels or not message.raw_text:
            return

        self.channels[channel_id]["reply_text"] = message.raw_text
        self._save_channels()
        await message.delete()

        try:
            await saved_call.edit(
                f"💥 текст установлен !\n\n{message.raw_text}",
                reply_markup=[[{"text": "⬅️ Назад", "callback": self._cb_back, "style": "danger"}]],
            )
        except Exception:
            await self.client.send_message(message.sender_id, f"💥 текст установлен !\n\n{message.raw_text}", formatting_entities=self._emoji(PREMIUM_EMOJI_ID))

    async def _handle_channel_post(self, message: Message):
        if not self.config["enabled"]:
            return

        if not message.is_channel or message.is_group:
            return

        data = self.channels.get(str(message.chat_id))
        if not data:
            return

        try:
            discussion = await self.client(
                functions.messages.GetDiscussionMessageRequest(peer=message.chat_id, msg_id=message.id)
            )
        except Exception:
            await self.client.send_message("me", f"💔{message.chat_id} — пост удалён или нет дискуссии", formatting_entities=self._emoji(ERROR_EMOJI_ID))
            return

        if self.config["delay_seconds"] > 0:
            await asyncio.sleep(self.config["delay_seconds"])

        chat = discussion.chats[0]
        reply_to = discussion.messages[0].id
        text = data.get("reply_text", DEFAULT_REPLY_TEXT)

        try:
            await self.client.send_message(chat, text, reply_to=reply_to)
        except Exception as e:
            if "not all of the users" in str(e).lower() or "join" in str(e).lower():
                try:
                    await self.client(functions.channels.JoinChannelRequest(chat))
                    await self.client.send_message(chat, text, reply_to=reply_to)
                    return
                except Exception:
                    pass
            await self.client.send_message("me", f"💔{data.get('link', message.chat_id)} — не удалось отправить: {e}", formatting_entities=self._emoji(ERROR_EMOJI_ID))

    async def watcher(self, message: Message):
        await self._handle_text_input(message)
        await self._handle_channel_post(message)
