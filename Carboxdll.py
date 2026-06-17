# meta developer: @bmodules

import aiohttp
from telethon.tl.types import DocumentAttributeFilename

from .. import loader, utils


@loader.tds
class CarboxDLLMod(loader.Module):
    strings = {
        "name": "CarboxDLL",
        "no_media": "❌ Ответь на фото/видео/файл командой <code>{}snoe</code>",
        "too_big": "❌ Файл слишком большой: <code>{}</code> (лимит <code>{}</code>)",
        "uploading": "<emoji document_id=5255971360965930740>⏳</emoji> Загружаю...",
        "timeout": "❌ Превышено время ожидания, попробуй ещё раз.",
        "done": (
            "<emoji document_id=6028446612408241647>✅</emoji> Готово!\n"
            "<blockquote><emoji document_id=5877307202888273539>🔗</emoji> <code>{}</code></blockquote>"
        ),
        "error": "❌ Ошибка: <code>{}</code>",
    }

    config = loader.ModuleConfig(
        loader.ConfigValue(
            "catbox_userhash",
            "",
            "Userhash для catbox.moe (необязательно)",
        )
    )

    async def client_ready(self):
        await self.request_join("@bmodules", "Канал автора модуля")

    async def snoecmd(self, message):
        """Загрузить файл на catbox.moe."""
        reply = await message.get_reply_message()

        media_msg = next(
            (m for m in (reply, message) if m and (m.photo or m.video or m.document or m.sticker or m.gif)),
            None,
        )

        if not media_msg:
            await utils.answer(message, self.strings("no_media").format(self.get_prefix()))
            return

        if media_msg.document and media_msg.document.size > 209715200:
            await utils.answer(
                message,
                self.strings("too_big").format(
                    f"{media_msg.document.size / 1024 / 1024:.1f} MB",
                    "200 MB",
                ),
            )
            return

        status = await utils.answer(message, self.strings("uploading"))

        try:
            file_bytes = await self.client.download_media(media_msg, bytes)
        except Exception as e:
            await utils.answer(status, self.strings("error").format(utils.escape_html(str(e)[:300])))
            return

        if not file_bytes:
            await utils.answer(status, self.strings("error").format("не удалось скачать медиа"))
            return

        if media_msg.document:
            doc = media_msg.document
            mime = doc.mime_type or ""
            filename = (
                next((a.file_name for a in doc.attributes if isinstance(a, DocumentAttributeFilename)), None)
                or ("video.mp4" if "video" in mime else "image.jpg" if "image" in mime else "file.bin")
            )
        elif media_msg.photo:
            filename = "photo.jpg"
        else:
            filename = "file.bin"

        try:
            link = await self._upload(file_bytes, filename)
        except TimeoutError:
            await utils.answer(status, self.strings("timeout"))
            return
        except Exception as e:
            await utils.answer(status, self.strings("error").format(utils.escape_html(str(e)[:300])))
            return

        await utils.answer(status, self.strings("done").format(utils.escape_html(link)))

    async def _upload(self, file_bytes, filename):
        errors = []

        async def jget(resp):
            try:
                return await resp.json(content_type=None)
            except Exception:
                return None

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as s:
            try:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                if self.config["catbox_userhash"]:
                    form.add_field("userhash", self.config["catbox_userhash"])
                form.add_field("fileToUpload", file_bytes, filename=filename)
                async with s.post("https://catbox.moe/user/api.php", data=form) as r:
                    text = await r.text()
                    if r.status == 200 and text.strip().startswith("http"):
                        return text.strip()
                    errors.append(f"catbox {r.status}")
            except Exception as e:
                errors.append(f"catbox {e}")

            try:
                form = aiohttp.FormData()
                form.add_field("reqtype", "fileupload")
                form.add_field("time", "72h")
                form.add_field("fileToUpload", file_bytes, filename=filename)
                async with s.post("https://litterbox.catbox.moe/resources/internals/api.php", data=form) as r:
                    text = await r.text()
                    if r.status == 200 and text.strip().startswith("http"):
                        return text.strip()
                    errors.append(f"litterbox {r.status}")
            except Exception as e:
                errors.append(f"litterbox {e}")

            for name, url in [
                ("uguu", "https://uguu.se/upload"),
                ("fileditch", "https://up1.fileditch.com/upload.php"),
                ("qu.ax", "https://qu.ax/upload.php"),
            ]:
                try:
                    form = aiohttp.FormData()
                    form.add_field("files[]", file_bytes, filename=filename)
                    async with s.post(url, data=form) as r:
                        data = await jget(r) if r.status == 200 else None
                        if isinstance(data, dict) and (files := data.get("files")) and files[0].get("url"):
                            return files[0]["url"]
                        errors.append(f"{name} {r.status}")
                except Exception as e:
                    errors.append(f"{name} {e}")

            try:
                form = aiohttp.FormData()
                form.add_field("file", file_bytes, filename=filename)
                async with s.post("https://0x0.st", data=form) as r:
                    text = await r.text()
                    if r.status == 200 and text.strip().startswith("http"):
                        return text.strip()
                    errors.append(f"0x0 {r.status}")
            except Exception as e:
                errors.append(f"0x0 {e}")

            try:
                form = aiohttp.FormData()
                form.add_field("file", file_bytes, filename=filename)
                async with s.post("https://tmpfiles.org/api/v1/upload", data=form) as r:
                    data = await jget(r) if r.status == 200 else None
                    if isinstance(data, dict) and (url := data.get("data", {}).get("url")):
                        return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    errors.append(f"tmpfiles {r.status}")
            except Exception as e:
                errors.append(f"tmpfiles {e}")

            try:
                form = aiohttp.FormData()
                form.add_field("file", file_bytes, filename=filename)
                async with s.post("https://pixeldrain.com/api/file", data=form) as r:
                    data = await jget(r) if r.status in (200, 201) else None
                    if isinstance(data, dict) and data.get("id"):
                        return f"https://pixeldrain.com/u/{data['id']}"
                    errors.append(f"pixeldrain {r.status}")
            except Exception as e:
                errors.append(f"pixeldrain {e}")

            try:
                async with s.get("https://api.gofile.io/servers") as r:
                    sd = await jget(r)
                servers = (sd or {}).get("data", {}).get("servers") or []
                if servers and (server := servers[0].get("name")):
                    form = aiohttp.FormData()
                    form.add_field("file", file_bytes, filename=filename)
                    async with s.post(f"https://{server}.gofile.io/contents/uploadfile", data=form) as r:
                        data = await jget(r) if r.status == 200 else None
                        if isinstance(data, dict) and (link := data.get("data", {}).get("downloadPage")):
                            return link
                        errors.append(f"gofile {r.status}")
                else:
                    errors.append("gofile no server")
            except Exception as e:
                errors.append(f"gofile {e}")

        raise RuntimeError(", ".join(errors))
