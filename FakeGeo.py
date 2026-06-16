# ██████╗  ██████╗ ███╗   ██╗███████╗███████╗
# ██╔══██╗██╔═══██╗████╗  ██║██╔════╝██╔════╝
# ██████╔╝██║   ██║██╔██╗ ██║█████╗  ███████╗
# ██╔══██╗██║   ██║██║╚██╗██║██╔══╝  ╚════██║
# ██████╔╝╚██████╔╝██║ ╚████║███████╗███████║
# ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚══════╝
#
# meta developer: @bmodules

from .. import loader, utils
from telethon.tl.types import InputMediaGeoPoint, InputGeoPoint, InputMediaGeoLive
import aiohttp
import asyncio
import random
import math

EARTH_RADIUS_KM = 6371


@loader.tds
class FakeGeoMod(loader.Module):
    """Отправка фейковой геолокации и live-трансляции по адресу, городу или стране"""

    strings = {"name": "FakeGeo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_broadcast = None
        self.broadcast_history = []

    async def _get_coords(self, query: str):
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": "HikkaUserbot/FakeGeo/1.0"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        if not data:
            return None

        result = data[0]
        return {
            "lat": float(result["lat"]),
            "lon": float(result["lon"]),
            "name": result.get("display_name", query),
        }

    def _calculate_movement(self, start_lat: float, start_lon: float, distance_km: float, angle: float):
        lat_rad = math.radians(start_lat)
        lon_rad = math.radians(start_lon)
        angle_rad = math.radians(angle)

        new_lat_rad = math.asin(
            math.sin(lat_rad) * math.cos(distance_km / EARTH_RADIUS_KM) +
            math.cos(lat_rad) * math.sin(distance_km / EARTH_RADIUS_KM) * math.cos(angle_rad)
        )

        new_lon_rad = lon_rad + math.atan2(
            math.sin(angle_rad) * math.sin(distance_km / EARTH_RADIUS_KM) * math.cos(lat_rad),
            math.cos(distance_km / EARTH_RADIUS_KM) - math.sin(lat_rad) * math.sin(new_lat_rad)
        )

        return {
            "lat": math.degrees(new_lat_rad),
            "lon": math.degrees(new_lon_rad),
        }

    def _haversine(self, lat1, lon1, lat2, lon2):
        lat_diff = math.radians(lat2 - lat1)
        lon_diff = math.radians(lon2 - lon1)
        a = math.sin(lat_diff / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(lon_diff / 2) ** 2
        return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))

    @loader.command()
    async def geo(self, message):
        """Использование: .geo <адрес/город/страна>"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "📍 <b>Использование:</b>\n"
                "<code>.geo город</code>\n"
                "<code>.geo страна город</code>\n"
                "<code>.geo улица, город</code>\n\n"
                "<b>Примеры:</b>\n"
                "<code>.geo Moscow</code>\n"
                "<code>.geo Germany Berlin</code>\n"
                "<code>.geo Арбат, Москва</code>"
            )
            return

        await message.edit("🔍 Поиск координат...")

        try:
            location = await self._get_coords(args.strip())

            if not location:
                await message.edit("❌ <b>Адрес не найден.</b>")
                return

            media = InputMediaGeoPoint(
                geo_point=InputGeoPoint(
                    lat=location["lat"],
                    long=location["lon"],
                )
            )

            await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            await message.delete()

        except Exception as e:
            error_str = str(e)
            if "TOPIC_CLOSED" in error_str:
                await message.edit("❌ <b>Топик закрыт.</b>")
            else:
                await message.edit(f"❌ <b>Ошибка:</b> <code>{error_str[:100]}</code>")

    @loader.command()
    async def geofake(self, message):
        """Использование: .geofake <адрес/город> [минуты] [дрожание True/False]"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "📌 <b>Фейк локация (без движения):</b>\n"
                "<code>.geofake город [минуты] [дрожание]</code>\n\n"
                "<b>Примеры:</b>\n"
                "<code>.geofake Moscow 5</code>\n"
                "<code>.geofake Berlin 10 true</code> ← с небольшим дрожанием"
            )
            return

        parts = args.strip().split()
        period_minutes = 5
        tremor = False

        if len(parts) >= 2 and parts[-1].lower() in ["true", "false"]:
            tremor = parts[-1].lower() == "true"
            parts = parts[:-1]

        if len(parts) >= 1 and parts[-1].isdigit():
            period_minutes = int(parts[-1])
            query = " ".join(parts[:-1])
        else:
            query = " ".join(parts)

        period_minutes = max(1, min(480, period_minutes))
        period_seconds = period_minutes * 60

        await message.edit("🔍 Поиск координат...")

        try:
            location = await self._get_coords(query)

            if not location:
                await message.edit("❌ <b>Адрес не найден.</b>")
                return

            current_lat = location["lat"]
            current_lon = location["lon"]

            media = InputMediaGeoLive(
                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                period=period_seconds,
                stopped=False,
            )

            location_msg = await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            self.active_broadcast = {
                "location_msg": location_msg,
                "chat_id": message.chat_id,
                "active": True,
            }

            await message.delete()

            if tremor:
                update_interval = 10
                total_updates = period_seconds // update_interval

                for update_num in range(total_updates):
                    if not self.active_broadcast or not self.active_broadcast["active"]:
                        break

                    while self.active_broadcast and self.active_broadcast.get("paused"):
                        await asyncio.sleep(1)

                    if not self.active_broadcast or not self.active_broadcast["active"]:
                        break

                    await asyncio.sleep(update_interval)

                    tremor_distance = random.uniform(0.01, 0.05)
                    tremor_angle = random.uniform(0, 360)

                    new_pos = self._calculate_movement(current_lat, current_lon, tremor_distance, tremor_angle)
                    current_lat = new_pos["lat"]
                    current_lon = new_pos["lon"]

                    try:
                        media = InputMediaGeoLive(
                            geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                            period=period_seconds - (update_num * update_interval),
                            stopped=False,
                        )
                        await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                    except Exception:
                        pass

            if self.active_broadcast:
                self.active_broadcast = None

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")

    @loader.command()
    async def georoute(self, message):
        """Использование: .georoute <город1>, <город2> [минуты] [скорость]"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "🛣️ <b>Маршрут между городами:</b>\n"
                "<code>.georoute город1, город2 [минуты] [скорость]</code>\n\n"
                "<b>Примеры:</b>\n"
                "<code>.georoute Moscow, Berlin 120 60</code>\n"
                "<code>.georoute New York, Los Angeles 90 80</code>"
            )
            return

        parts = args.strip().split()
        period_minutes = 60
        speed_kmh = 60

        if len(parts) >= 2 and parts[-1].isdigit():
            speed_kmh = int(parts[-1])
            parts = parts[:-1]

        if len(parts) >= 2 and parts[-1].isdigit():
            period_minutes = int(parts[-1])
            parts = parts[:-1]

        if len(parts) < 2:
            await message.edit("❌ <b>Укажи два города.</b>")
            return

        full_query = " ".join(parts)
        if "," in full_query:
            city1, city2 = (p.strip() for p in full_query.split(",", 1))
        else:
            city1 = " ".join(parts[:len(parts)//2])
            city2 = " ".join(parts[len(parts)//2:])

        await message.edit("🔍 Поиск маршрута...")

        try:
            loc1 = await self._get_coords(city1)
            loc2 = await self._get_coords(city2)

            if not loc1 or not loc2:
                await message.edit("❌ <b>Один из городов не найден.</b>")
                return

            start_lat, start_lon = loc1["lat"], loc1["lon"]
            end_lat, end_lon = loc2["lat"], loc2["lon"]

            distance = self._haversine(start_lat, start_lon, end_lat, end_lon)

            period_minutes = max(1, min(480, period_minutes))
            speed_kmh = max(1, min(9000, speed_kmh))

            travel_time_hours = distance / speed_kmh
            actual_period_minutes = min(int(travel_time_hours * 60), period_minutes)
            period_seconds = max(60, actual_period_minutes * 60)

            angle = math.degrees(math.atan2(end_lon - start_lon, end_lat - start_lat))

            current_lat = start_lat
            current_lon = start_lon

            media = InputMediaGeoLive(
                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                period=period_seconds,
                stopped=False,
            )

            location_msg = await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            self.active_broadcast = {
                "location_msg": location_msg,
                "chat_id": message.chat_id,
                "active": True,
                "speed": speed_kmh,
            }

            await message.delete()

            update_interval = 5
            total_updates = period_seconds // update_interval

            for update_num in range(1, total_updates + 1):
                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                while self.active_broadcast and self.active_broadcast.get("paused"):
                    await asyncio.sleep(1)

                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                await asyncio.sleep(update_interval)

                live_speed = self.active_broadcast.get("speed", speed_kmh)
                distance_per_update = (live_speed * update_interval) / 3600

                new_pos = self._calculate_movement(current_lat, current_lon, distance_per_update, angle)
                current_lat = new_pos["lat"]
                current_lon = new_pos["lon"]

                try:
                    media = InputMediaGeoLive(
                        geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                        period=period_seconds - (update_num * update_interval),
                        stopped=False,
                    )
                    await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                except Exception:
                    pass

            if self.active_broadcast:
                self.active_broadcast = None

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")

    @loader.command()
    async def geod(self, message):
        """Использование: .geod <адрес/город> [минуты] [скорость]"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "🚗 <b>Live-трансляция с движением:</b>\n"
                "<code>.geod город [минуты] [скорость]</code>\n\n"
                "<b>Примеры:</b>\n"
                "<code>.geod Moscow 10 5</code>\n"
                "<code>.geod Berlin 30 60</code>\n\n"
                "⚠️ <code>.ste</code> для остановки"
            )
            return

        parts = args.strip().split()
        period_minutes = 15
        speed_kmh = 15

        if len(parts) >= 2 and parts[-1].isdigit():
            speed_kmh = int(parts[-1])
            parts = parts[:-1]

        if len(parts) >= 1 and parts[-1].isdigit():
            period_minutes = int(parts[-1])
            query = " ".join(parts[:-1])
        else:
            query = " ".join(parts)

        period_minutes = max(1, min(480, period_minutes))
        speed_kmh = max(1, min(9000, speed_kmh))
        period_seconds = period_minutes * 60

        await message.edit("🔍 Поиск координат...")

        try:
            location = await self._get_coords(query)

            if not location:
                await message.edit("❌ <b>Адрес не найден.</b>")
                return

            start_lat = location["lat"]
            start_lon = location["lon"]

            current_angle = random.uniform(0, 360)

            update_interval = 5
            total_updates = period_seconds // update_interval

            current_lat = start_lat
            current_lon = start_lon

            media = InputMediaGeoLive(
                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                period=period_seconds,
                stopped=False,
            )

            location_msg = await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            self.active_broadcast = {
                "location_msg": location_msg,
                "chat_id": message.chat_id,
                "active": True,
                "paused": False,
                "speed": speed_kmh,
                "current_lat": current_lat,
                "current_lon": current_lon,
            }

            self.broadcast_history = [(current_lat, current_lon)]

            await message.delete()

            for update_num in range(1, total_updates + 1):
                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                while self.active_broadcast and self.active_broadcast.get("paused"):
                    await asyncio.sleep(1)

                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                await asyncio.sleep(update_interval)

                current_angle += random.uniform(-10, 10)
                current_angle = current_angle % 360

                live_speed = self.active_broadcast.get("speed", speed_kmh)
                distance_per_update = (live_speed * update_interval) / 3600

                new_pos = self._calculate_movement(
                    current_lat,
                    current_lon,
                    distance_per_update,
                    current_angle
                )

                current_lat = new_pos["lat"]
                current_lon = new_pos["lon"]
                self.broadcast_history.append((current_lat, current_lon))
                self.active_broadcast["current_lat"] = current_lat
                self.active_broadcast["current_lon"] = current_lon

                try:
                    media = InputMediaGeoLive(
                        geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                        period=period_seconds - (update_num * update_interval),
                        stopped=False,
                    )
                    await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                except Exception:
                    pass

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")
        finally:
            self.active_broadcast = None

    @loader.command()
    async def geospeed(self, message):
        """Использование: .geospeed <км/ч>"""
        args = utils.get_args_raw(message)

        if not args or not args.isdigit():
            await message.edit("❌ <b>Укажи скорость:</b> <code>.geospeed 100</code>")
            return

        if not self.active_broadcast:
            await message.edit("❌ <b>Нет активной трансляции.</b>")
            return

        speed = max(1, min(120, int(args)))
        self.active_broadcast["speed"] = speed

        await message.edit(f"🟢 <b>Скорость изменена на {speed} км/ч</b>")

    @loader.command()
    async def geostop(self, message):
        """Использование: .geostop"""
        if not self.active_broadcast:
            await message.edit("❌ <b>Нет активной трансляции.</b>")
            return

        if self.active_broadcast.get("paused"):
            self.active_broadcast["paused"] = False
            await message.edit("🟢 <b>Трансляция возобновлена</b>")
        else:
            self.active_broadcast["paused"] = True
            await message.edit("⏸️ <b>Трансляция на паузе</b>")

    @loader.command()
    async def geomulti(self, message):
        """Использование: .geomulti город1 мин1 скорость1 город2 мин2 скорость2 ..."""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "🏙️ <b>Несколько локаций по очереди:</b>\n"
                "<code>.geomulti Москва 10 30 Берлин 15 60 Лондон 10 50</code>"
            )
            return

        await message.edit("🔍 Поиск маршрута...")

        try:
            parts = args.strip().split()
            routes = []

            i = 0
            while i < len(parts):
                j = i
                while j + 1 < len(parts) and not (parts[j].isdigit() and parts[j + 1].isdigit()):
                    j += 1

                if j + 1 >= len(parts):
                    break

                city = " ".join(parts[i:j])
                minutes = int(parts[j])
                speed = int(parts[j + 1])
                if not city:
                    break

                routes.append((city, minutes, speed))
                i = j + 2

            if not routes:
                await message.edit("❌ <b>Неверный формат.</b>")
                return

            current_lat = None
            current_lon = None
            location_msg = None

            for city, minutes, speed in routes:
                minutes = max(1, min(480, minutes))
                speed = max(1, min(120, speed))
                seconds = minutes * 60

                location = await self._get_coords(city)
                if not location:
                    continue

                if current_lat is None:
                    current_lat = location["lat"]
                    current_lon = location["lon"]
                else:
                    dest_lat = location["lat"]
                    dest_lon = location["lon"]

                    angle = math.degrees(math.atan2(dest_lon - current_lon, dest_lat - current_lat))
                    distance = self._haversine(current_lat, current_lon, dest_lat, dest_lon)
                    travel_seconds = max(60, int((distance / speed) * 3600))
                    seconds = min(seconds, travel_seconds)

                    if location_msg is None:
                        location_msg = await message.client.send_message(message.chat_id, f"🏙️ <b>Маршрут: {city}</b>")
                    else:
                        await location_msg.edit(f"🏙️ <b>Маршрут: {city}</b>")

                    self.active_broadcast = {
                        "location_msg": location_msg,
                        "chat_id": message.chat_id,
                        "active": True,
                    }

                    update_interval = 5
                    total_updates = seconds // update_interval
                    distance_per_update = distance / max(1, total_updates)

                    for update_num in range(1, total_updates + 1):
                        if not self.active_broadcast or not self.active_broadcast["active"]:
                            break

                        while self.active_broadcast and self.active_broadcast.get("paused"):
                            await asyncio.sleep(1)

                        if not self.active_broadcast or not self.active_broadcast["active"]:
                            break

                        await asyncio.sleep(update_interval)

                        new_pos = self._calculate_movement(current_lat, current_lon, distance_per_update, angle)
                        current_lat = new_pos["lat"]
                        current_lon = new_pos["lon"]

                        try:
                            media = InputMediaGeoLive(
                                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                                period=seconds - (update_num * update_interval),
                                stopped=False,
                            )
                            await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                        except Exception:
                            pass

                    current_lat = dest_lat
                    current_lon = dest_lon

            if location_msg:
                await location_msg.edit("🟢 <b>Маршрут завершен!</b>")

            if self.active_broadcast:
                self.active_broadcast = None

            await message.delete()

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")

    @loader.command()
    async def geotrack(self, message):
        """Использование: .geotrack"""
        if not self.broadcast_history:
            await message.edit("❌ <b>История координат пуста.</b>")
            return

        history_text = "📍 <b>История координат:</b>\n\n"
        for i, (lat, lon) in enumerate(self.broadcast_history[-20:], 1):
            history_text += f"{i}. <code>{lat:.6f}, {lon:.6f}</code>\n"

        if len(self.broadcast_history) > 20:
            history_text += f"\n<i>...и еще {len(self.broadcast_history) - 20} точек</i>"

        await message.edit(history_text)

    @loader.command()
    async def geostatus(self, message):
        """Использование: .geostatus"""
        if not self.active_broadcast:
            await message.edit("❌ <b>Нет активной трансляции.</b>")
            return

        status = "⏸️ на паузе" if self.active_broadcast.get("paused") else "▶️ в процессе"
        speed = self.active_broadcast.get("speed", "N/A")
        lat = self.active_broadcast.get("current_lat", "N/A")
        lon = self.active_broadcast.get("current_lon", "N/A")

        await message.edit(
            f"🚗 <b>Статус трансляции:</b>\n\n"
            f"Статус: {status}\n"
            f"Скорость: {speed} км/ч\n"
            f"📍 Позиция: <code>{lat}, {lon}</code>\n\n"
            f"<b>Команды:</b>\n"
            f"<code>.geospeed 100</code> - изменить скорость\n"
            f"<code>.geostop</code> - пауза/возобновить\n"
            f"<code>.ste</code> - остановить"
        )

    @loader.command()
    async def geodirect(self, message):
        """Использование: .geodirect <направление> <адрес> <скорость> <минуты>"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "🧭 <b>Направленное движение:</b>\n"
                "<code>.geodirect north Moscow 100 30</code>\n"
                "<code>.geodirect northeast Berlin 80 20</code>\n\n"
                "<b>Направления:</b> north, northeast, east, southeast, south, southwest, west, northwest"
            )
            return

        parts = args.strip().split()
        if len(parts) < 4:
            await message.edit("❌ <b>Укажи: направление адрес скорость минуты</b>")
            return

        direction = parts[0]
        speed_kmh = int(parts[-2]) if parts[-2].isdigit() else 50
        period_minutes = int(parts[-1]) if parts[-1].isdigit() else 30
        update_interval = 5
        query = " ".join(parts[1:-2])

        directions = {
            "north": 0, "northeast": 45, "east": 90, "southeast": 135,
            "south": 180, "southwest": 225, "west": 270, "northwest": 315,
        }
        angle = directions.get(direction.lower())
        if angle is None:
            await message.edit(
                "❌ <b>Неверное направление.</b>\n"
                "Доступные: north, northeast, east, southeast, south, southwest, west, northwest"
            )
            return

        speed_kmh = max(1, min(9000, speed_kmh))
        period_minutes = max(1, min(480, period_minutes))
        period_seconds = period_minutes * 60

        await message.edit("🧭 Инициализация...")

        try:
            location = await self._get_coords(query)
            if not location:
                await message.edit("❌ <b>Адрес не найден.</b>")
                return

            start_lat = location["lat"]
            start_lon = location["lon"]

            current_lat = start_lat
            current_lon = start_lon

            media = InputMediaGeoLive(
                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                period=period_seconds,
                stopped=False,
            )

            location_msg = await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            self.active_broadcast = {
                "location_msg": location_msg,
                "chat_id": message.chat_id,
                "active": True,
                "speed": speed_kmh,
            }

            await message.delete()

            update_count = period_seconds // update_interval

            for update_num in range(1, update_count + 1):
                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                while self.active_broadcast and self.active_broadcast.get("paused"):
                    await asyncio.sleep(1)

                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                await asyncio.sleep(update_interval)

                live_speed = self.active_broadcast.get("speed", speed_kmh)
                distance_per_update = (live_speed * update_interval) / 3600

                new_pos = self._calculate_movement(current_lat, current_lon, distance_per_update, angle)
                current_lat = new_pos["lat"]
                current_lon = new_pos["lon"]

                try:
                    media = InputMediaGeoLive(
                        geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                        period=period_seconds - (update_num * update_interval),
                        stopped=False,
                    )
                    await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                except Exception:
                    pass

            if self.active_broadcast:
                self.active_broadcast = None

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")

    @loader.command()
    async def geopattern(self, message):
        """Использование: .geopattern <pattern> <адрес> [скорость] [минуты]"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "🎯 <b>Паттерны движения:</b>\n"
                "<code>.geopattern circle Moscow 50 30</code>\n"
                "<code>.geopattern zigzag Berlin 80 20</code>\n"
                "<code>.geopattern square London 40 15</code>\n\n"
                "<b>Паттерны:</b> circle, zigzag, square"
            )
            return

        parts = args.strip().split()
        if len(parts) < 2:
            await message.edit("❌ <b>Укажи: паттерн адрес</b>")
            return

        pattern = parts[0].lower()
        query = " ".join(parts[1:-2]) if len(parts) > 2 else parts[1]
        speed_kmh = int(parts[-2]) if len(parts) > 2 and parts[-2].isdigit() else 50
        period_minutes = int(parts[-1]) if len(parts) > 1 and parts[-1].isdigit() else 20

        if pattern not in ["circle", "zigzag", "square"]:
            await message.edit("❌ <b>Неверный паттерн.</b>")
            return

        speed_kmh = max(1, min(9000, speed_kmh))
        period_minutes = max(1, min(480, period_minutes))
        period_seconds = period_minutes * 60

        await message.edit("🔍 Поиск координат...")

        try:
            location = await self._get_coords(query)
            if not location:
                await message.edit("❌ <b>Адрес не найден.</b>")
                return

            center_lat = location["lat"]
            center_lon = location["lon"]

            current_lat = center_lat
            current_lon = center_lon

            media = InputMediaGeoLive(
                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                period=period_seconds,
                stopped=False,
            )

            location_msg = await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            self.active_broadcast = {
                "location_msg": location_msg,
                "chat_id": message.chat_id,
                "active": True,
                "speed": speed_kmh,
            }

            await message.delete()

            total_distance = (speed_kmh * period_minutes) / 60
            radius = total_distance / (2 * math.pi) if pattern == "circle" else total_distance / 4

            update_interval = 5
            total_updates = period_seconds // update_interval

            for update_num in range(1, total_updates + 1):
                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                while self.active_broadcast and self.active_broadcast.get("paused"):
                    await asyncio.sleep(1)

                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                await asyncio.sleep(update_interval)

                angle = (update_num / total_updates) * 360

                if pattern == "circle":
                    new_pos = self._calculate_movement(center_lat, center_lon, radius, angle)
                    current_lat = new_pos["lat"]
                    current_lon = new_pos["lon"]

                elif pattern == "zigzag":
                    zigzag_step = total_distance / total_updates
                    is_right = (update_num // 20) % 2 == 0
                    zigzag_angle = 90 if is_right else 270
                    new_pos = self._calculate_movement(current_lat, current_lon, zigzag_step, zigzag_angle)
                    current_lat = new_pos["lat"]
                    current_lon = new_pos["lon"]

                elif pattern == "square":
                    side_updates = total_updates // 4
                    side = update_num // side_updates
                    angles = [0, 90, 180, 270]
                    angle_for_side = angles[side % 4]
                    distance_in_side = (radius * 4) / total_updates
                    new_pos = self._calculate_movement(current_lat, current_lon, distance_in_side, angle_for_side)
                    current_lat = new_pos["lat"]
                    current_lon = new_pos["lon"]

                try:
                    media = InputMediaGeoLive(
                        geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                        period=period_seconds - (update_num * update_interval),
                        stopped=False,
                    )
                    await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                except Exception:
                    pass

            if self.active_broadcast:
                self.active_broadcast = None

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")

    @loader.command()
    async def geospoof(self, message):
        """Использование: .geospoof <адрес> [минуты] [км_прыжка] [интервал_сек]"""
        args = utils.get_args_raw(message)

        if not args:
            await message.edit(
                "⚡ <b>Случайные прыжки:</b>\n"
                "<code>.geospoof Moscow 10 5 10</code> ← 10 мин, прыжки на 5 км каждые 10 сек"
            )
            return

        parts = args.strip().split()
        period_minutes = 10
        jump_km = 5
        jump_interval = 10
        query = args.strip()

        if len(parts) >= 4 and all(p.isdigit() for p in parts[-3:]):
            jump_interval = int(parts[-1])
            jump_km = int(parts[-2])
            period_minutes = int(parts[-3])
            query = " ".join(parts[:-3])
        elif len(parts) >= 3 and all(p.isdigit() for p in parts[-2:]):
            jump_km = int(parts[-2])
            period_minutes = int(parts[-1])
            query = " ".join(parts[:-2])

        period_minutes = max(1, min(480, period_minutes))
        jump_km = max(0.1, min(50, jump_km))
        jump_interval = max(1, min(120, jump_interval))
        period_seconds = period_minutes * 60

        await message.edit("🔍 Поиск координат...")

        try:
            location = await self._get_coords(query)
            if not location:
                await message.edit("❌ <b>Адрес не найден.</b>")
                return

            current_lat = location["lat"]
            current_lon = location["lon"]

            media = InputMediaGeoLive(
                geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                period=period_seconds,
                stopped=False,
            )

            location_msg = await message.client.send_file(
                message.chat_id,
                file=media,
                reply_to=message.reply_to_msg_id,
            )

            self.active_broadcast = {
                "location_msg": location_msg,
                "chat_id": message.chat_id,
                "active": True,
            }

            await message.delete()

            total_jumps = period_seconds // jump_interval

            for jump_num in range(1, total_jumps + 1):
                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                while self.active_broadcast and self.active_broadcast.get("paused"):
                    await asyncio.sleep(1)

                if not self.active_broadcast or not self.active_broadcast["active"]:
                    break

                await asyncio.sleep(jump_interval)

                angle = random.uniform(0, 360)
                new_pos = self._calculate_movement(current_lat, current_lon, jump_km, angle)
                current_lat = new_pos["lat"]
                current_lon = new_pos["lon"]

                try:
                    media = InputMediaGeoLive(
                        geo_point=InputGeoPoint(lat=current_lat, long=current_lon),
                        period=period_seconds - (jump_num * jump_interval),
                        stopped=False,
                    )
                    await location_msg.client.edit_message(message.chat_id, location_msg.id, file=media)
                except Exception:
                    pass

            if self.active_broadcast:
                self.active_broadcast = None

        except Exception as e:
            await message.edit(f"❌ <b>Ошибка:</b> <code>{str(e)[:100]}</code>")

    @loader.command()
    async def ste(self, message):
        """Использование: .ste"""
        if not self.active_broadcast:
            await message.edit("❌ <b>Нет активной трансляции.</b>")
            return

        self.active_broadcast["active"] = False

        try:
            await self.active_broadcast["location_msg"].delete()
        except Exception:
            pass

        self.active_broadcast = None
        await message.delete()