import random
import re
from vkbottle import Bot
from vkbottle.bot import Message
from database import Database

# Токен вставлен напрямую (замените на свой, если нужно)
TOKEN = "vk1.a.PgKs5zmaKwfG6Wl9afWSnmCRL-p9kFHIFSUyCpxo4ze2riZlPS_PJdYLe2aqNDrsgqykkw851OHyPtBtdxkCj5znBICD0q5tni9wZkkityrK5PMQJYMJc-3t_N6o_34oSvvtniTfcDHL49u2n2em1uv9YoZ7z6DQHenxIeVtpObVqUTmPCThe1d5TM0cYSy3J9wozdT3Ml40ya7bvOp8Fg"

bot = Bot(token=TOKEN)
db = Database()

# ---- Парсинг и броски ----
def parse_roll(command: str):
    """
    Разбирает команду броска и возвращает (текст результата, успех_парсинга)
    Поддерживаемые форматы:
      /dX
      /dX+N /dX-N
      /NdX
      /NdX+N /NdX-N
      /d20 adv /d20 advantage /d20 dis /d20 disadvantage (с опциональным модификатором)
    """
    cmd = command.strip().lower()
    if not cmd.startswith('/'):
        return None, False
    cmd = cmd[1:]  # убираем '/'

    # --- Проверка на преимущество/помеху для d20 ---
    # Паттерн: d20 (возможно с модификатором) и затем adv/dis (или advantage/disadvantage)
    match_adv = re.match(r'^d20([+-]\d+)?\s+(adv|advantage|dis|disadvantage)$', cmd)
    if match_adv:
        mod_str = match_adv.group(1)
        modifier = int(mod_str) if mod_str else 0
        adv_type = match_adv.group(2)  # 'adv', 'advantage', 'dis', 'disadvantage'
        is_advantage = adv_type.startswith('adv')
        
        rolls = [random.randint(1, 20), random.randint(1, 20)]
        if is_advantage:
            chosen = max(rolls)
            desc = "преимуществом"
        else:
            chosen = min(rolls)
            desc = "помехой"
        
        total = chosen + modifier
        rolls_str = f"{rolls[0]}, {rolls[1]}"
        if modifier == 0:
            return f"🎲 Бросок d20 с {desc}: [{rolls_str}] → выбран {chosen} → **{total}**", True
        else:
            return f"🎲 Бросок d20 с {desc}: [{rolls_str}] → выбран {chosen} {modifier:+d} = **{total}**", True

    # --- Обычные броски (без adv/dis) ---
    # 1. dX с опциональным модификатором
    match_dice = re.match(r'^d(\d+)([+-]\d+)?$', cmd)
    if match_dice:
        sides = int(match_dice.group(1))
        mod_str = match_dice.group(2)
        modifier = int(mod_str) if mod_str else 0
        roll = random.randint(1, sides)
        total = roll + modifier
        if modifier == 0:
            return f"🎲 Результат броска: {roll}", True
        else:
            return f"🎲 Результат броска: {roll} {modifier} = {total}", True

    # 2. NdX с опциональным модификатором
    match_ndice = re.match(r'^(\d+)d(\d+)([+-]\d+)?$', cmd)
    if match_ndice:
        count = int(match_ndice.group(1))
        sides = int(match_ndice.group(2))
        mod_str = match_ndice.group(3)
        modifier = int(mod_str) if mod_str else 0
        if count > 100:
            return "❌ Слишком много кубиков (максимум 100)", False
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + modifier
        rolls_str = ", ".join(map(str, rolls))
        if modifier == 0:
            return f"🎲 Результат броска: [{rolls_str}] = {total}", True
        else:
            return f"🎲 Результат броска: [{rolls_str}] = {sum(rolls)} {modifier} = {total}", True

    return None, False

def special_roll(command: str):
    """Обрабатывает специальные команды: /attack, /defense, /double, /roll"""
    cmd = command.strip().lower()
    if cmd == '/roll':
        num = random.randint(0, 100)
        return f"🎲 Случайное число (0-100): {num}", True
    elif cmd == '/attack':
        roll = random.randint(1, 20)
        if roll == 1:
            return f"⚔️ Куб атаки: **{roll}** — **Промах** (крит. промах)", True
        elif roll == 20:
            return f"⚔️ Куб атаки: **{roll}** — **Крит**", True
        else:
            return f"⚔️ Куб атаки: **{roll}** — **Попадание**", True
    elif cmd == '/defense':
        roll = random.randint(1, 20)
        if roll == 1:
            return f"🛡️ Куб защиты: **{roll}** — **Провал** (крит. провал)", True
        elif roll == 20:
            return f"🛡️ Куб защиты: **{roll}** — **Крит** (крит. успех)", True
        else:
            if roll >= 10:
                return f"🛡️ Куб защиты: **{roll}** — **Успех**", True
            else:
                return f"🛡️ Куб защиты: **{roll}** — **Провал**", True
    elif cmd == '/double':
        roll = random.randint(1, 6)
        if roll <= 3:
            return f"🔁 Куб удвоения: **{roll}** → **Пусто**", True
        else:
            return f"🔁 Куб удвоения: **{roll}** → **×2**", True
    return None, False

# ---- Обработка имени ----
async def handle_name(message: Message, cmd: str):
    parts = cmd.strip().split(maxsplit=1)
    if len(parts) == 1:
        name = await db.get_name(message.peer_id, message.from_id)
        if name:
            return f"👤 Ваше имя в этой беседе: **{name}**"
        else:
            return "👤 У вас ещё нет имени. Установите: `/имя ВашеИмя`"
    else:
        new_name = parts[1].strip()
        if len(new_name) > 30:
            return "❌ Имя слишком длинное (максимум 30 символов)"
        await db.set_name(message.peer_id, message.from_id, new_name)
        return f"✅ Ваше имя в этой беседе установлено: **{new_name}**"

# ---- Помощь ----
def get_help_text():
    return """📚 **Доступные команды**:

**Стандартные броски:**
/dX — бросок одного кубика (X = 4,6,8,10,12,20,100)
/dX+N или /dX-N — с модификатором
/NdX — бросок нескольких кубиков (например /2d6)
/NdX+N — несколько кубиков с модификатором

**Преимущество / Помеха (только для d20):**
/d20 adv  или /d20 advantage  — бросок с преимуществом
/d20 dis  или /d20 disadvantage — бросок с помехой
Также с модификатором: `/d20 adv+3` или `/d20+2 dis`

**Специальные команды:**
/roll — случайное число от 0 до 100
/attack — куб атаки (промах / попадание / крит)
/defense — куб защиты (провал / успех / крит)
/double — куб удвоения (пусто / ×2)

**Профиль:**
/имя НовоеИмя — задать своё имя в этой беседе
/имя — показать текущее имя

**Прочее:**
/помощь — показать это сообщение

Можно писать несколько команд в одном сообщении, разделяя их пробелами.
Пример: `/d20 adv /d6+3 /attack`"""

# ---- Главный обработчик сообщений ----
@bot.on.message()
async def handle_message(message: Message):
    text = message.text.strip()
    if not text:
        return

    if text.startswith('/помощь'):
        await message.answer(get_help_text())
        return

    parts = text.split()
    responses = []

    for part in parts:
        if not part.startswith('/'):
            continue

        # Обработка команды имени
        if part.startswith('/имя'):
            idx = parts.index(part)
            name_parts = [part]
            j = idx + 1
            while j < len(parts) and not parts[j].startswith('/'):
                name_parts.append(parts[j])
                j += 1
            full_name_cmd = ' '.join(name_parts)
            result = await handle_name(message, full_name_cmd)
            responses.append(result)
            continue

        # Специальные команды
        special_result, ok = special_roll(part)
        if ok:
            responses.append(special_result)
            continue

        # Стандартные броски (включая adv/dis)
        roll_result, ok = parse_roll(part)
        if ok:
            responses.append(roll_result)
            continue

        responses.append(f"❌ Неизвестная команда: `{part}`")

    if responses:
        await message.answer("\n".join(responses))

if __name__ == "__main__":
    bot.run_forever()
