import aiosqlite
from datetime import datetime, timedelta

DB_PATH = "bot_data.db"

class Database:
    def __init__(self):
        self.conn = None

    async def _ensure_connection(self):
        if self.conn is None:
            self.conn = await aiosqlite.connect(DB_PATH)
            # Таблица имён пользователей в беседах
            await self.conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    peer_id INTEGER,
                    user_id INTEGER,
                    nickname TEXT,
                    PRIMARY KEY (peer_id, user_id)
                )
            ''')
            # Таблица статистики активности (по дням)
            await self.conn.execute('''
                CREATE TABLE IF NOT EXISTS activity (
                    peer_id INTEGER,
                    user_id INTEGER,
                    date TEXT,
                    msg_count INTEGER DEFAULT 0,
                    roll_count INTEGER DEFAULT 0,
                    PRIMARY KEY (peer_id, user_id, date)
                )
            ''')
            await self.conn.commit()

    # ----- Управление именами -----
    async def get_name(self, peer_id: int, user_id: int) -> str | None:
        await self._ensure_connection()
        async with self.conn.execute(
            "SELECT nickname FROM users WHERE peer_id = ? AND user_id = ?",
            (peer_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_name(self, peer_id: int, user_id: int, name: str):
        await self._ensure_connection()
        await self.conn.execute(
            "INSERT OR REPLACE INTO users (peer_id, user_id, nickname) VALUES (?, ?, ?)",
            (peer_id, user_id, name)
        )
        await self.conn.commit()

    async def get_all_names(self, peer_id: int):
        await self._ensure_connection()
        async with self.conn.execute(
            "SELECT user_id, nickname FROM users WHERE peer_id = ?",
            (peer_id,)
        ) as cursor:
            return await cursor.fetchall()

    # ----- Статистика активности -----
    async def update_activity(self, peer_id: int, user_id: int, is_roll: bool = False):
        """Увеличивает счётчик сообщений или бросков за текущий день."""
        today = datetime.now().strftime("%Y-%m-%d")
        await self._ensure_connection()
        async with self.conn.execute(
            "SELECT msg_count, roll_count FROM activity WHERE peer_id = ? AND user_id = ? AND date = ?",
            (peer_id, user_id, today)
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            msg_c, roll_c = row
            if is_roll:
                roll_c += 1
            else:
                msg_c += 1
            await self.conn.execute(
                "UPDATE activity SET msg_count = ?, roll_count = ? WHERE peer_id = ? AND user_id = ? AND date = ?",
                (msg_c, roll_c, peer_id, user_id, today)
            )
        else:
            msg_c = 0 if is_roll else 1
            roll_c = 1 if is_roll else 0
            await self.conn.execute(
                "INSERT INTO activity (peer_id, user_id, date, msg_count, roll_count) VALUES (?, ?, ?, ?, ?)",
                (peer_id, user_id, today, msg_c, roll_c)
            )
        await self.conn.commit()

    async def get_top(self, peer_id: int, days: int = 0):
        """
        Возвращает топ пользователей по сообщениям и броскам.
        days == 0 – за всё время, иначе за последние days дней (до 365).
        """
        await self._ensure_connection()
        if days <= 0:
            query = """
                SELECT user_id, SUM(msg_count) as msg, SUM(roll_count) as roll
                FROM activity
                WHERE peer_id = ?
                GROUP BY user_id
                ORDER BY msg DESC, roll DESC
            """
            params = (peer_id,)
        else:
            days = min(days, 365)
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            query = """
                SELECT user_id, SUM(msg_count) as msg, SUM(roll_count) as roll
                FROM activity
                WHERE peer_id = ? AND date >= ?
                GROUP BY user_id
                ORDER BY msg DESC, roll DESC
            """
            params = (peer_id, start_date)

        async with self.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        result = []
        for user_id, msg, roll in rows:
            name = await self.get_name(peer_id, user_id)
            if not name:
                name = f"id{user_id}"
            result.append((name, msg, roll))
        return result

    async def remove_left_users(self, peer_id: int, current_member_ids: set[int]):
        """Удаляет из БД записи пользователей, которых больше нет в беседе."""
        await self._ensure_connection()
        # Получаем всех пользователей, для которых есть записи в этой беседе
        async with self.conn.execute(
            "SELECT DISTINCT user_id FROM users WHERE peer_id = ?",
            (peer_id,)
        ) as cursor:
            db_users = {row[0] for row in await cursor.fetchall()}
        left = db_users - current_member_ids
        if left:
            placeholders = ','.join('?' * len(left))
            # Удаляем имена
            await self.conn.execute(
                f"DELETE FROM users WHERE peer_id = ? AND user_id IN ({placeholders})",
                (peer_id, *left)
            )
            # Удаляем статистику
            await self.conn.execute(
                f"DELETE FROM activity WHERE peer_id = ? AND user_id IN ({placeholders})",
                (peer_id, *left)
            )
            await self.conn.commit()
        return left
