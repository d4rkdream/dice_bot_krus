import os
import random
import re
from vkbottle import Bot
from vkbottle.bot import Message
from database import Database

TOKEN = os.environ.get("VK_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения VK_TOKEN не установлена!")

bot = Bot(token=TOKEN)
db = Database()

# ---- Парсинг и броски (с поддержкой /d = d20) ----
def parse_roll(command: str):
    cmd = command.strip().lower()
    if not (cmd.startswith('/d') or cmd.startswith('/к')):
        return None, False
    cmd = cmd[1:]  # убираем '/'
    cmd = cmd.replace('к', 'd', 1)  # заменяем русскую 'к' на 'd'

    # --- Если после /d или /к ничего нет (например просто "/d" или "/к+3") ---
    # Проверяем, что cmd начинается с 'd' и затем либо сразу конец, либо +/-, либо пробел (adv/dis)
    # Примеры: "d", "d+2", "d-1", "d adv", "d+3 adv"
    match_empty = re.match(r'^d([+-]\d+)?(?:\s+(adv|advantage|dis|disadvantage))?$', cmd)
    if match_empty:
        mod_str = match_empty.group(1)
        modifier = int(mod_str) if mod_str else 0
        adv_str = match_empty.group(2)
        if adv_str:
            is_advantage = adv_str.startswith('adv')
            rolls = [random.randint(1, 20), random.randint(1, 20)]
            chosen = max(rolls) if is_advantage else min(rolls)
            desc = "преимуществом" if is_advantage else "помехой"
            total = chosen + modifier
            rolls_str = f"{rolls[0]}, {rolls[1]}"
            if modifier == 0:
                return f"🎲 Бросок d20 с {desc}: [{rolls_str}] → выбран {chosen} → **{total}**", True
            else:
                return f"🎲 Бросок d20 с {desc}: [{rolls_str}] → выбран {chosen} {modifier:+d} = **{total}**", True
        else:
            roll = random.randint(1, 20)
            total = roll + modifier
            if modifier == 0:
                return f"🎲 Результат броска d20: {roll}", True
            else:
                return f"🎲 Результат броска d20: {roll} {modifier} = {total}", True

    # --- Преимущество/помеха для явного d20 ---
    match_adv = re.match(r'^d20([+-]\d+)?\s+(adv|advantage|dis|disadvantage)$', cmd)
    if match_adv:
        mod_str = match_adv.group(1)
        modifier = int(mod_str) if mod_str else 0
        adv_type = match_adv.group(2)
        is_advantage = adv_type.startswith('adv')
        rolls = [random.randint(1, 20), random.randint(1, 20)]
        chosen = max(rolls) if is_advantage else min(rolls)
        desc = "преимуществом" if is_advantage else "помехой"
        total = chosen + modifier
        rolls_str = f"{rolls[0]}, {rolls[1]}"
        if modifier == 0:
            return f"🎲 Бросок d20 с {desc}: [{rolls_str}] → выбран {chosen} → **{total}**", True
        else:
            return f"🎲 Бросок d20 с {desc}: [{rolls_str}] → выбран {chosen} {modifier:+d} = **{total}**", True

    # --- Обычные броски dX (X указан) ---
    match_dice = re.match(r'^d(\d+)([+-]\d+)?$', cmd)
    if match_dice:
        sides = int(match_dice.group(1))
        mod_str = match_dice.group(2)
        modifier = int(mod_str) if mod_str else 0
        roll = random.randint(1, sides)
        total = roll + modifier
        if modifier == 0:
            return f"🎲 Результат броска d{sides}: {roll}", True
        else:
            return f"🎲 Результат броска d{sides}: {roll} {modifier} = {total}", True

    # --- Несколько кубиков NdX ---
    match_ndice = re.match(r'^(\d+)d(\d+)([+-]\d+)?$', cmd)
    if match_ndice:
        count = int(match_ndice.group(1))
        sides = int(match_ndice.group(2))
        mod_str = match_ndice.group(3)
        modifier = int(mod_str) if mod_str else 0
        if count > 100:
            return "❌ Слишком много граней (максимум 100)", False
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + modifier
        rolls_str = ", ".join(map(str, rolls))
        if modifier == 0:
            return f"🎲 Результат броска {count}d{sides}: [{rolls_str}] = {total}", True
        else:
            return f"🎲 Результат броска {count}d{sides}: [{rolls_str}] = {sum(rolls)} {modifier} = {total}", True

    return None, False

# ---- Остальные функции (special_roll, handle_name, get_help_text) ----
def special_roll(command: str):
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
            return f"🛡️ Куб защиты: **{roll}** — **Успех**" if roll >= 10 else f"🛡️ Куб защиты: **{roll}** — **Провал**", True
    elif cmd == '/double':
        roll = random.randint(1, 6)
        if roll <= 3:
            return f"🔁 Куб удвоения: **{roll}** → **Пусто**", True
        else:
            return f"🔁 Куб удвоения: **{roll}** → **×2**", True
    return None, False

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

def get_help_text():
    return """📚 **Доступные команды**:

**Стандартные броски:**
/d или /к — бросок d20 (по умолчанию)
/dX или /кX — бросок кубика X (X = 4,6,8,10,12,20,100)
/dX+N или /кX+N — с модификатором
/NdX или /NкX — бросок нескольких кубиков (например /2d6)
/NdX+N или /NкX+N — несколько кубиков с модификатором

**Преимущество / Помеха (только для d20):**
/d20 adv  или /к20 adv  — бросок с преимуществом
/d20 dis  или /к20 dis  — бросок с помехой
/d adv    или /к adv    — тоже работает (как /d20 adv)
/d+2 dis  или /к-1 adv  — с модификатором

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
Пример: `/d adv /к6+3 /attack`"""

# ---- Главный обработчик ----
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

        special_result, ok = special_roll(part)
        if ok:
            responses.append(special_result)
            continue

        roll_result, ok = parse_roll(part)
        if ok:
            responses.append(roll_result)
            continue

        responses.append(f"❌ Неизвестная команда: `{part}`")

    if responses:
        await message.answer("\n".join(responses))

if __name__ == "__main__":
    bot.run_forever()
