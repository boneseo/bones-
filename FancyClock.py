# # ██████╗  ██████╗ ███╗   ██╗███████╗███████╗
# ██╔══██╗██╔═══██╗████╗  ██║██╔════╝██╔════╝
# ██████╔╝██║   ██║██╔██╗ ██║█████╗  ███████╗
# ██╔══██╗██║   ██║██║╚██╗██║██╔══╝  ╚════██║
# ██████╔╝╚██████╔╝██║ ╚████║███████╗███████║
# ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚══════╝

# meta developer: @ewefa
import asyncio
import re
import logging
import aiohttp
from datetime import datetime
from zoneinfo import ZoneInfo

from telethon.tl.functions.account import UpdateProfileRequest
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

DEFAULT_TZ = "Europe/Moscow"

CLOCK_RE = re.compile(r"\s*\|.*$")

EMO_CLOCK = "<emoji document_id=5877530150345641603>⏳</emoji>"
EMO_OK    = "<emoji document_id=5256182535917940722>✅</emoji>"
EMO_SCHED = "<emoji document_id=5253527438675158560>⏰</emoji>"

FONT_LIST = [
    ("Default",     "0123456789"),
    ("Bold Math",   "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"),
    ("Bold Sans",   "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    ("Bold Italic", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    ("Mono",        "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"),
    ("Fullwidth",   "０１２３４５６７８９"),
    ("Superscript", "⁰¹²³⁴⁵⁶⁷⁸⁹"),
    ("Subscript",   "₀₁₂₃₄₅₆₇₈₉"),
    ("Circle",      "⓪①②③④⑤⑥⑦⑧⑨"),
    ("Black Circle","⓿❶❷❸❹❺❻❼❽❾"),
]

DEFAULT_FONT = "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"


def _strip(name: str) -> str:
    return CLOCK_RE.sub("", name).rstrip()


def _make_map(font: str) -> dict:
    return {str(i): c for i, c in enumerate(font)}


def _fancy(t: str, digit_map: dict) -> str:
    return "".join(digit_map.get(c, c) for c in t)


@loader.tds
class FancyClockMod(loader.Module):
    strings = {"name": "FancyClock"}

    def __init__(self):
        self._task = None
        self._running = False
        self._font = DEFAULT_FONT
        self._stop_task = None

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self._font = self.db.get("FancyClock", "font", DEFAULT_FONT)

        if self._enabled():
            self._running = True
            self._task = asyncio.ensure_future(self._loop())

    def _get_tz(self) -> ZoneInfo:
        name = self.db.get("FancyClock", "tz", DEFAULT_TZ)
        try:
            return ZoneInfo(name)
        except Exception:
            return ZoneInfo(DEFAULT_TZ)

    def _base(self) -> str:
        return self.db.get("FancyClock", "base", "")

    def _enabled(self) -> bool:
        return self.db.get("FancyClock", "enabled", False)

    async def _refresh_name(self, fancy_time: str):
        if not self._enabled():
            return
        base = self._base()
        if base:
            await self._set_name(f"{base} | {fancy_time}")

    async def _set_name(self, name: str):
        name = name[:64]
        try:
            await self.client(UpdateProfileRequest(first_name=name))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 3)
            try:
                await self.client(UpdateProfileRequest(first_name=name))
            except Exception:
                pass
        except Exception:
            pass

    async def _loop(self):
        while self._running:
            try:
                tz = self._get_tz()
                now = datetime.now(tz)
                base = self._base()
                if not base:
                    break

                fancy_time = _fancy(now.strftime("%H:%M"), _make_map(self._font))
                name = f"{base} | {fancy_time}"
                await self._set_name(name)

                await asyncio.sleep(60 - now.second)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("FancyClock: %s", e)
                await asyncio.sleep(10)

    async def _stop_at(self, target_h: int, target_m: int):
        tz = self._get_tz()
        while True:
            now = datetime.now(tz)
            if now.hour == target_h and now.minute == target_m:
                break
            await asyncio.sleep(15)

        await self._disable_clock()

    async def _disable_clock(self):
        self._running = False
        self.db.set("FancyClock", "enabled", False)

        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

        base = self._base()
        if base:
            await self._set_name(base)

    async def fccmd(self, message: Message):
        """включить / выключить часы в нике"""
        if self._enabled():
            await self._disable_clock()

            if self._stop_task and not self._stop_task.done():
                self._stop_task.cancel()
                self._stop_task = None

            await message.edit(f"{EMO_OK} Часы выключены", parse_mode="html")
        else:
            me = await self.client.get_me()
            base = _strip(me.first_name or "")
            self.db.set("FancyClock", "base", base)
            self.db.set("FancyClock", "enabled", True)
            self._running = True

            if self._task and not self._task.done():
                self._task.cancel()

            self._task = asyncio.ensure_future(self._loop())
            await message.edit(f"{EMO_CLOCK} Часы включены", parse_mode="html")

    async def fctcmd(self, message: Message):
        """выключить часы в указанное время. Пример: .fct 16.09"""
        args = utils.get_args_raw(message).strip()
        if not args:
            await message.edit(f"{EMO_SCHED} Укажи время. Пример: <code>.fct 16.09</code>", parse_mode="html")
            return

        match = re.fullmatch(r"(\d{1,2})[:\.](\d{2})", args)
        if not match:
            await message.edit(f"{EMO_SCHED} Неверный формат. Пример: <code>.fct 16.09</code>", parse_mode="html")
            return

        h, m = int(match.group(1)), int(match.group(2))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            await message.edit(f"{EMO_SCHED} Некорректное время.", parse_mode="html")
            return

        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()

        self._stop_task = asyncio.ensure_future(self._stop_at(h, m))
        await message.edit(f"{EMO_SCHED} Часы выключатся в <b>{h:02d}:{m:02d}</b>", parse_mode="html")

    async def fcscmd(self, message: Message):
        """поменять часовой пояс по названию города или страны. Пример: .fcs Красноярск"""
        query = utils.get_args_raw(message).strip()
        if not query:
            await message.edit(
                f"{EMO_CLOCK} Укажи город или страну.\n"
                f"Примеры: <code>.fcs Красноярск</code> · <code>.fcs Россия Тула</code>",
                parse_mode="html",
            )
            return

        await message.edit(f"{EMO_CLOCK} Ищу <b>{query}</b>...", parse_mode="html")

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://geocoding-api.open-meteo.com/v1/search"
                params = {"name": query, "count": 1, "language": "ru", "format": "json"}

                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()

                results = data.get("results")
                if not results:
                    await message.edit(f"{EMO_SCHED} Не нашёл <b>{query}</b>. Попробуй по-другому.", parse_mode="html")
                    return

                result = results[0]
                tz_name = result.get("timezone")
                city_label = result.get("name", query)
                country = result.get("country", "")
                if country:
                    city_label = f"{city_label}, {country}"

                if not tz_name:
                    await message.edit(f"{EMO_SCHED} Не удалось определить часовой пояс для <b>{query}</b>.", parse_mode="html")
                    return

                self.db.set("FancyClock", "tz", tz_name)
                now = datetime.now(ZoneInfo(tz_name))
                preview = _fancy(now.strftime("%H:%M"), _make_map(self._font))

                await self._refresh_name(preview)

                await message.edit(
                    f"{EMO_OK} <b>{city_label}</b>\n"
                    f"Таймзона: <code>{tz_name}</code>\n"
                    f"Время: {preview}",
                    parse_mode="html",
                )

        except Exception:
            await message.edit(f"{EMO_SCHED} Не удалось получить данные. Попробуй позже.", parse_mode="html")

    async def fcfcmd(self, message: Message):
        """шрифты для цифр в нике"""
        now_str = datetime.now(self._get_tz()).strftime("%H:%M")

        rows = []
        row = []
        for idx, (label, chars) in enumerate(FONT_LIST):
            preview = _fancy(now_str, _make_map(chars))
            btn_text = f"{preview} — {label}"
            btn = {"text": btn_text, "callback": self._pick_font, "args": (chars, label)}
            btn["style"] = "danger" if chars == self._font else "success"
            row.append(btn)
            if len(row) == 2 or idx == len(FONT_LIST) - 1:
                rows.append(row)
                row = []

        current_label = next((l for l, c in FONT_LIST if c == self._font), "custom")
        current_preview = _fancy(now_str, _make_map(self._font))

        await self.inline.form(
            text=(
                f"{EMO_CLOCK} <b>Шрифты для цифр</b>\n\n"
                f"Сейчас: {current_preview} — {current_label}"
            ),
            message=message,
            reply_markup=rows,
        )

    async def _pick_font(self, call, chars: str, label: str):
        self._font = chars
        self.db.set("FancyClock", "font", chars)

        now = datetime.now(self._get_tz())
        preview = _fancy(now.strftime("%H:%M"), _make_map(chars))

        await self._refresh_name(preview)

        await call.edit(
            f"Шрифт <b>{label}</b> выбран\n\nПример: {preview}"
        )
