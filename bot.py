import os
import re
import random
import sqlite3
import asyncio
from datetime import datetime, timedelta
from aiohttp import web
from vkbottle import Bot
from vkbottle.bot import Message
from vkbottle.api import API

TOKEN = os.environ.get("VK_TOKEN")
if not TOKEN:
    raise ValueError("VK_BOT_TOKEN не установлен")

DB_PATH = "users.db"
bot = Bot(token=TOKEN)
api = API(token=TOKEN)

# --- Инициализация БД ---
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        # Таблица имён
        con.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "vk_id INTEGER NOT NULL,"
            "peer_id INTEGER NOT NULL,"
            "nickname TEXT NOT NULL,"
            "PRIMARY KEY (vk_id, peer_id)"
            ")"
        )
        # Таблица статистики активности (по дням)
        con.execute(
            "CREATE TABLE IF NOT EXISTS activity ("
            "peer_id INTEGER NOT NULL,"
            "user_id INTEGER NOT NULL,"
            "date TEXT NOT NULL,"
            "msg_count INTEGER DEFAULT 0,"
            "roll_count INTEGER DEFAULT 0,"
            "PRIMARY KEY (peer_id, user_id, date)"
            ")"
        )

def get_nickname(vk_id: int, peer_id: int) -> str | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT nickname FROM users WHERE vk_id = ? AND peer_id = ?",
            (vk_id, peer_id)
        ).fetchone()
    return row[0] if row else None

def set_nickname(vk_id: int, peer_id: int, nickname: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO users (vk_id, peer_id, nickname) VALUES (?, ?, ?)"
            " ON CONFLICT(vk_id, peer_id) DO UPDATE SET nickname = excluded.nickname",
            (vk_id, peer_id, nickname)
        )

def get_all_nicknames(peer_id: int) -> list[tuple[int, str]]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT vk_id, nickname FROM users WHERE peer_id = ?",
            (peer_id,)
        ).fetchall()
    return rows

# --- Статистика ---
def update_activity(peer_id: int, user_id: int, is_roll: bool = False):
    """Увеличивает счётчик сообщений или бросков для пользователя за текущий день."""
    today = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "SELECT msg_count, roll_count FROM activity WHERE peer_id = ? AND user_id = ? AND date = ?",
            (peer_id, user_id, today)
        )
        row = cur.fetchone()
        if row:
            msg_c, roll_c = row
            if is_roll:
                roll_c += 1
            else:
                msg_c += 1
            con.execute(
                "UPDATE activity SET msg_count = ?, roll_count = ? WHERE peer_id = ? AND user_id = ? AND date = ?",
                (msg_c, roll_c, peer_id, user_id, today)
            )
        else:
            msg_c = 0 if is_roll else 1
            roll_c = 1 if is_roll else 0
            con.execute(
                "INSERT INTO activity (peer_id, user_id, date, msg_count, roll_count) VALUES (?, ?, ?, ?, ?)",
                (peer_id, user_id, today, msg_c, roll_c)
            )

def get_top(peer_id: int, days: int = 0):
    """
    Возвращает топ пользователей по сообщениям и броскам.
    Если days == 0, то за всё время, иначе за последние days дней (не более 365).
    """
    with sqlite3.connect(DB_PATH) as con:
        if days <= 0:
            # За всё время
            cur = con.execute(
                "SELECT user_id, SUM(msg_count) as msg, SUM(roll_count) as roll "
                "FROM activity WHERE peer_id = ? GROUP BY user_id "
                "ORDER BY msg DESC, roll DESC",
                (peer_id,)
            )
        else:
            # Ограничиваем дни
            if days > 365:
                days = 365
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            cur = con.execute(
                "SELECT user_id, SUM(msg_count) as msg, SUM(roll_count) as roll "
                "FROM activity WHERE peer_id = ? AND date >= ? GROUP BY user_id "
                "ORDER BY msg DESC, roll DESC",
                (peer_id, start_date)
            )
        rows = cur.fetchall()
        # Добавляем имена
        result = []
        for user_id, msg, roll in rows:
            name = get_nickname(user_id, peer_id) or f"id{user_id}"
            result.append((name, msg, roll))
        return result

def remove_left_users(peer_id: int, current_member_ids: set[int]):
    """Удаляет из БД записи пользователей, которые не входят в current_member_ids."""
    with sqlite3.connect(DB_PATH) as con:
        # Получаем всех пользователей, для которых есть записи в этой беседе
        cur = con.execute(
            "SELECT DISTINCT vk_id FROM users WHERE peer_id = ?",
            (peer_id,)
        )
        db_users = {row[0] for row in cur.fetchall()}
        left = db_users - current_member_ids
        if left:
            # Удаляем имена
            con.execute(
                "DELETE FROM users WHERE peer_id = ? AND vk_id IN ({})".format(','.join('?' * len(left))),
                (peer_id, *left)
            )
            # Удаляем статистику
            con.execute(
                "DELETE FROM activity WHERE peer_id = ? AND user_id IN ({})".format(','.join('?' * len(left))),
                (peer_id, *left)
            )
        return left

# --- Логика бросков (без изменений, кроме удаления звёздочек) ---
def parse_dice_command(cmd: str):
    cmd = cmd.strip().lower()
    if not cmd.startswith('/d'):
        return None, False
    cmd = cmd[1:]

    adv_match = re.match(r'^d20([+-]\d+)?\s+(adv|advantage|dis|disadvantage)$', cmd)
    if adv_match:
        mod_str = adv_match.group(1)
        modifier = int(mod_str) if mod_str else 0
        adv_type = adv_match.group(2)
        is_adv = adv_type.startswith('adv')
        rolls = [random.randint(1, 20), random.randint(1, 20)]
        chosen = max(rolls) if is_adv else min(rolls)
        total = chosen + modifier
        desc = "преимуществом" if is_adv else "помехой"
        roll_str = f"{rolls[0]}, {rolls[1]}"
        if modifier == 0:
            return f"🎲 Бросок d20 с {desc}: [{roll_str}] → выбран {chosen} → {total}", True
        else:
            return f"🎲 Бросок d20 с {desc}: [{roll_str}] → выбран {chosen} {modifier:+d} = {total}", True

    empty_match = re.match(r'^d([+-]\d+)?$', cmd)
    if empty_match:
        mod_str = empty_match.group(1)
        modifier = int(mod_str) if mod_str else 0
        roll = random.randint(1, 20)
        total = roll + modifier
        if modifier == 0:
            return f"🎲 Результат броска d20: {roll}", True
        else:
            return f"🎲 Результат броска d20: {roll} {modifier} = {total}", True

    single_match = re.match(r'^d(\d+)([+-]\d+)?$', cmd)
    if single_match:
        sides = int(single_match.group(1))
        mod_str = single_match.group(2)
        modifier = int(mod_str) if mod_str else 0
        if sides < 2:
            return "❌ Куб должен иметь минимум 2 грани", False
        if sides > 100:
            return "❌ Слишком много граней (максимум 100)", False
        roll = random.randint(1, sides)
        total = roll + modifier
        if modifier == 0:
            return f"🎲 Результат броска d{sides}: {roll}", True
        else:
            return f"🎲 Результат броска d{sides}: {roll} {modifier} = {total}", True

    multi_match = re.match(r'^(\d+)d(\d+)([+-]\d+)?$', cmd)
    if multi_match:
        count = int(multi_match.group(1))
        sides = int(multi_match.group(2))
        mod_str = multi_match.group(3)
        modifier = int(mod_str) if mod_str else 0
        if sides < 2:
            return "❌ Куб должен иметь минимум 2 грани", False
        if sides > 100:
            return "❌ Слишком много граней (максимум 100)", False
        if count < 1:
            return "❌ Количество кубиков должно быть не менее 1", False
        if count > 100:
            return "❌ Слишком много кубиков (максимум 100)", False
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + modifier
        roll_str = ", ".join(map(str, rolls))
        if modifier == 0:
            return f"🎲 Результат броска {count}d{sides}: [{roll_str}] = {total}", True
        else:
            return f"🎲 Результат броска {count}d{sides}: [{roll_str}] = {sum(rolls)} {modifier} = {total}", True

    return None, False

def special_roll(cmd: str):
    cmd = cmd.lower()
    if cmd == '/roll':
        num = random.randint(0, 100)
        return f"🎲 Случайное число (0–100): {num}", True
    if cmd == '/attack':
        roll = random.randint(1, 20)
        if roll == 1:
            return f"⚔️ Куб атаки: {roll} — Промах (крит. промах)", True
        if roll == 20:
            return f"⚔️ Куб атаки: {roll} — Крит", True
        return f"⚔️ Куб атаки: {roll} — Попадание", True
    if cmd == '/defense':
        roll = random.randint(1, 20)
        if roll == 1:
            return f"🛡️ Куб защиты: {roll} — Провал (крит. провал)", True
        if roll == 20:
            return f"🛡️ Куб защиты: {roll} — Крит (крит. успех)", True
        return f"🛡️ Куб защиты: {roll} — Успех" if roll >= 10 else f"🛡️ Куб защиты: {roll} — Провал", True
    if cmd == '/double':
        roll = random.randint(1, 6)
        if roll <= 3:
            return f"🔁 Куб удвоения: {roll} → Пусто", True
        else:
            return f"🔁 Куб удвоения: {roll} → ×2", True
    return None, False

def normalize_command(raw: str) -> str:
    lower = raw.lower()
    if lower == '/кпре':
        return '/d20 adv'
    if lower == '/кпом':
        return '/d20 dis'
    if lower.startswith('/к'):
        rest = raw[2:]
        return '/d' + rest
    return raw

HELP_TEXT = """📚 Доступные команды:

Стандартные броски:
/d или /к — бросок d20
/dX или /кX — бросок кубика с любым числом граней X (2–100)
/dX+N или /кX+N — с модификатором
/NdX или /NкX — бросок нескольких кубиков (X 2–100, N 1–100)
/NdX+N или /NкX+N — с модификатором

Преимущество / Помеха (только d20):
/d20 adv, /d20 advantage, /к20 adv — с преимуществом
/d20 dis, /d20 disadvantage, /к20 dis — с помехой
/d adv, /к adv — тоже работает
Модификатор: /d20+2 adv

Специальные команды:
/roll — случайное число 0–100
/attack — куб атаки (промах/попадание/крит)
/defense — куб защиты (провал/успех/крит)
/double — куб удвоения (пусто/×2)

Профиль:
/имя НовоеИмя — задать своё имя
/имя — показать своё имя
/имена — показать список всех имён в беседе

Статистика:
/топ [дни] — топ участников по сообщениям и броскам (дни до 365, по умолчанию всё время)

Администрирование:
/вышедшие кик — удалить из базы данных вышедших участников (требуются права бота)

Прочее:
/помощь — это сообщение

Можно несколько команд в одном сообщении: /d20 adv /2к6+3 /attack"""

async def reply_with_mention(message: Message, text: str):
    """Отправляет ответ с упоминанием автора исходного сообщения, если у него есть имя."""
    user_id = message.from_id
    peer_id = message.peer_id
    nickname = get_nickname(user_id, peer_id)
    if nickname:
        mention = f"[id{user_id}|{nickname}]"
        full_text = f"{mention}, {text}"
    else:
        full_text = text
    await message.answer(full_text)

# --- Получение списка участников беседы ---
async def get_conversation_members(peer_id: int) -> set[int]:
    """Возвращает множество ID участников беседы."""
    try:
        members = await bot.api.messages.get_conversation_members(peer_id=peer_id)
        return {item.member_id for item in members.items}
    except Exception as e:
        print(f"Ошибка получения участников беседы {peer_id}: {e}")
        return set()

# --- Основной обработчик ---
@bot.on.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    lower = text.lower()
    user_id = message.from_id
    peer_id = message.peer_id

    # Увеличиваем счётчик сообщений (для любого текста, включая команды)
    update_activity(peer_id, user_id, is_roll=False)

    # Помощь
    if lower in ('/помощь', '/кпомощь', '/help', '/кhelp'):
        await message.answer(HELP_TEXT)
        return

    # Команда /имена
    if lower in ('/имена', '/кимена'):
        all_names = get_all_nicknames(peer_id)
        if not all_names:
            await message.answer("В этой беседе пока нет ни одного установленного имени.")
        else:
            lines = ["Список имён в этой беседе:"]
            for vk_id, name in all_names:
                lines.append(f"{name} (id{vk_id})")
            await message.answer("\n".join(lines))
        return

    # Команда /топ [дни]
    if lower.startswith('/топ') or lower.startswith('/к топ'):
        parts = text.split()
        days = 0
        if len(parts) > 1 and parts[1].isdigit():
            days = int(parts[1])
            if days > 365:
                days = 365
        top = get_top(peer_id, days)
        if not top:
            await message.answer("Нет данных для статистики.")
            return
        period = f"за последние {days} дней" if days > 0 else "за всё время"
        lines = [f"📊 Топ участников {period}:"]
        lines.append("По сообщениям:")
        for i, (name, msg, roll) in enumerate(top[:10], 1):
            lines.append(f"{i}. {name} — {msg} сообщ.")
        lines.append("По броскам кубов:")
        # Сортировка по броскам
        top_rolls = sorted(top, key=lambda x: x[2], reverse=True)
        for i, (name, msg, roll) in enumerate(top_rolls[:10], 1):
            lines.append(f"{i}. {name} — {roll} бросков")
        await message.answer("\n".join(lines))
        return

    # Команда /вышедшие кик
    if lower == '/вышедшие кик' or lower == '/к вышедшие кик':
        # Проверяем, является ли чат беседой (peer_id > 2000000000)
        if peer_id <= 2000000000:
            await message.answer("Эта команда работает только в беседах.")
            return
        # Получаем текущих участников
        members = await get_conversation_members(peer_id)
        if not members:
            await message.answer("Не удалось получить список участников. Убедитесь, что бот администратор беседы.")
            return
        # Удаляем вышедших
        left = remove_left_users(peer_id, members)
        if left:
            await message.answer(f"✅ Удалены данные о вышедших участниках: {len(left)} человек.")
        else:
            await message.answer("Нет вышедших участников, данные в порядке.")
        return

    # Команда /имя (только установка и просмотр своего имени)
    if lower.startswith('/имя') or lower.startswith('/кимя'):
        prefix_len = 5 if lower.startswith('/кимя') else 4
        rest = text[prefix_len:].strip()
        if not rest:
            name = get_nickname(user_id, peer_id)
            if name:
                await message.answer(f"👤 Ваше имя в этой беседе: {name}")
            else:
                await message.answer("👤 У вас ещё нет имени. Установите: /имя ВашеИмя")
        else:
            if len(rest) > 32:
                await message.answer("❌ Имя слишком длинное (максимум 32 символа)")
            else:
                set_nickname(user_id, peer_id, rest)
                await message.answer(f"✅ Ваше имя в этой беседе установлено: {rest}")
        return

    # Обработка бросков и спецкоманд
    tokens = text.split()
    results = []
    nickname = get_nickname(user_id, peer_id)
    prefix = f"{nickname}: " if nickname else ""

    for token in tokens:
        if not token.startswith('/'):
            continue
        norm = normalize_command(token)
        special_res, ok = special_roll(norm)
        if ok:
            # Увеличиваем счётчик бросков
            update_activity(peer_id, user_id, is_roll=True)
            if prefix:
                special_res = special_res.replace('🎲', f'🎲 {prefix}').replace('⚔️', f'⚔️ {prefix}').replace('🛡️', f'🛡️ {prefix}').replace('🔁', f'🔁 {prefix}')
            results.append(special_res)
            continue
        dice_res, ok = parse_dice_command(norm)
        if ok:
            # Увеличиваем счётчик бросков
            update_activity(peer_id, user_id, is_roll=True)
            if prefix:
                dice_res = dice_res.replace('🎲', f'🎲 {prefix}')
            results.append(dice_res)
            continue
        results.append(f"❌ Неизвестная команда: `{token}`")

    if results:
        final_text = "\n".join(results)
        await reply_with_mention(message, final_text)

# --- Веб-сервер для health check ---
async def health(request):
    return web.Response(text="OK")

async def run_web():
    port = int(os.environ.get("PORT", 8000))
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

async def main():
    init_db()
    print("Бот запущен...")
    await asyncio.gather(
        run_web(),
        bot.run_polling(),
    )

if __name__ == "__main__":
    asyncio.run(main())
