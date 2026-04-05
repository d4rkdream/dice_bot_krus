import os
import re
import random
import asyncio
from datetime import datetime
from aiohttp import web
from vkbottle import Bot
from vkbottle.bot import Message
from vkbottle.api import API

from database import Database

TOKEN = os.environ.get("VK_TOKEN")
if not TOKEN:
    raise ValueError("VK_TOKEN не установлен")

bot = Bot(token=TOKEN)
api = API(token=TOKEN)
db = Database()

# ---------------------- Логика бросков (без изменений) ----------------------
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
            return f"🎲 Результат броска d20: {roll} {modifier:+d} = {total}", True

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
            return f"🎲 Результат броска d{sides}: {roll} {modifier:+d} = {total}", True

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
            return f"🎲 Результат броска {count}d{sides}: [{roll_str}] = {sum(rolls)} {modifier:+d} = {total}", True

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

# ---------------------- Вспомогательные функции ----------------------
async def reply_with_mention(message: Message, text: str):
    user_id = message.from_id
    peer_id = message.peer_id
    nickname = await db.get_name(peer_id, user_id)
    if nickname:
        mention = f"[id{user_id}|{nickname}]"
        full_text = f"{mention}, {text}"
    else:
        full_text = text
    await message.answer(full_text)

async def get_conversation_members(peer_id: int) -> set[int]:
    try:
        members = await bot.api.messages.get_conversation_members(peer_id=peer_id)
        return {item.member_id for item in members.items}
    except Exception as e:
        print(f"Ошибка получения участников беседы {peer_id}: {e}")
        return set()

# ---------------------- Обработчик сообщений ----------------------
@bot.on.message()
async def handle_message(message: Message):
    text = (message.text or "").strip()
    if not text:
        return
    lower = text.lower()
    user_id = message.from_id
    peer_id = message.peer_id

    await db.update_activity(peer_id, user_id, is_roll=False)

    if lower in ('/помощь', '/кпомощь', '/help', '/кhelp'):
        await message.answer(HELP_TEXT)
        return

    if lower in ('/имена', '/кимена'):
        all_names = await db.get_all_names(peer_id)
        if not all_names:
            await message.answer("В этой беседе пока нет ни одного установленного имени.")
        else:
            lines = ["Список имён в этой беседе:"]
            for user_id, name in all_names:
                lines.append(f"{name} (id{user_id})")
            await message.answer("\n".join(lines))
        return

    if lower.startswith('/топ') or lower.startswith('/к топ'):
        parts = text.split()
        days = 0
        if len(parts) > 1 and parts[1].isdigit():
            days = int(parts[1])
            if days > 365:
                days = 365
        top = await db.get_top(peer_id, days)
        if not top:
            await message.answer("Нет данных для статистики.")
            return
        period = f"за последние {days} дней" if days > 0 else "за всё время"
        lines = [f"📊 Топ участников {period}:"]
        lines.append("По сообщениям:")
        for i, (name, msg, roll) in enumerate(top[:10], 1):
            lines.append(f"{i}. {name} — {msg} сообщ.")
        lines.append("По броскам кубов:")
        top_rolls = sorted(top, key=lambda x: x[2], reverse=True)
        for i, (name, msg, roll) in enumerate(top_rolls[:10], 1):
            lines.append(f"{i}. {name} — {roll} бросков")
        await message.answer("\n".join(lines))
        return

    if lower == '/вышедшие кик' or lower == '/к вышедшие кик':
        if peer_id <= 2000000000:
            await message.answer("Эта команда работает только в беседах.")
            return
        members = await get_conversation_members(peer_id)
        if not members:
            await message.answer("Не удалось получить список участников. Убедитесь, что бот администратор беседы.")
            return
        left = await db.remove_left_users(peer_id, members)
        if left:
            await message.answer(f"✅ Удалены данные о вышедших участниках: {len(left)} человек.")
        else:
            await message.answer("Нет вышедших участников, данные в порядке.")
        return

    if lower.startswith('/имя') or lower.startswith('/кимя'):
        prefix_len = 5 if lower.startswith('/кимя') else 4
        rest = text[prefix_len:].strip()
        if not rest:
            name = await db.get_name(peer_id, user_id)
            if name:
                await message.answer(f"👤 Ваше имя в этой беседе: {name}")
            else:
                await message.answer("👤 У вас ещё нет имени. Установите: /имя ВашеИмя")
        else:
            if len(rest) > 32:
                await message.answer("❌ Имя слишком длинное (максимум 32 символа)")
            else:
                await db.set_name(peer_id, user_id, rest)
                await message.answer(f"✅ Ваше имя в этой беседе установлено: {rest}")
        return

    tokens = text.split()
    results = []
    nickname = await db.get_name(peer_id, user_id)
    prefix = f"{nickname}: " if nickname else ""

    for token in tokens:
        if not token.startswith('/'):
            continue
        norm = normalize_command(token)
        special_res, ok = special_roll(norm)
        if ok:
            await db.update_activity(peer_id, user_id, is_roll=True)
            if prefix:
                special_res = special_res.replace('🎲', f'🎲 {prefix}').replace('⚔️', f'⚔️ {prefix}').replace('🛡️', f'🛡️ {prefix}').replace('🔁', f'🔁 {prefix}')
            results.append(special_res)
            continue
        dice_res, ok = parse_dice_command(norm)
        if ok:
            await db.update_activity(peer_id, user_id, is_roll=True)
            if prefix:
                dice_res = dice_res.replace('🎲', f'🎲 {prefix}')
            results.append(dice_res)
            continue
        results.append(f"❌ Неизвестная команда: `{token}`")

    if results:
        final_text = "\n".join(results)
        await reply_with_mention(message, final_text)

# ---------------------- Веб-сервер для health check ----------------------
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
    # Бесконечно ждём (веб-сервер работает в фоне)
    await asyncio.Event().wait()

# ---------------------- Исправленная main() ----------------------
async def main():
    await db._ensure_connection()
    print("Бот запущен...")
    
    loop = asyncio.get_running_loop()
    # Запускаем веб-сервер как фоновую задачу
    web_task = asyncio.create_task(run_web())
    
    # Запускаем polling бота, передавая ему текущий цикл
    await bot.run_polling(loop=loop)
    
    # Если досюда дошли (остановка бота), отменяем веб-сервер
    web_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
