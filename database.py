import sqlite3
from datetime import datetime, timedelta

DB_PATH = "bot_data.db"

class Database:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    peer_id INTEGER,
                    user_id INTEGER,
                    nickname TEXT,
                    PRIMARY KEY (peer_id, user_id)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS activity (
                    peer_id INTEGER,
                    user_id INTEGER,
                    date TEXT,
                    msg_count INTEGER DEFAULT 0,
                    roll_count INTEGER DEFAULT 0,
                    PRIMARY KEY (peer_id, user_id, date)
                )
            ''')

    # ----- Управление именами -----
    def get_name(self, peer_id: int, user_id: int) -> str | None:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT nickname FROM users WHERE peer_id = ? AND user_id = ?",
                (peer_id, user_id)
            )
            row = cur.fetchone()
            return row[0] if row else None

    def set_name(self, peer_id: int, user_id: int, name: str):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (peer_id, user_id, nickname) VALUES (?, ?, ?)",
                (peer_id, user_id, name)
            )

    def get_all_names(self, peer_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT user_id, nickname FROM users WHERE peer_id = ?",
                (peer_id,)
            )
            return cur.fetchall()

    # ----- Статистика -----
    def update_activity(self, peer_id: int, user_id: int, is_roll: bool = False):
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
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
                conn.execute(
                    "UPDATE activity SET msg_count = ?, roll_count = ? WHERE peer_id = ? AND user_id = ? AND date = ?",
                    (msg_c, roll_c, peer_id, user_id, today)
                )
            else:
                msg_c = 0 if is_roll else 1
                roll_c = 1 if is_roll else 0
                conn.execute(
                    "INSERT INTO activity (peer_id, user_id, date, msg_count, roll_count) VALUES (?, ?, ?, ?, ?)",
                    (peer_id, user_id, today, msg_c, roll_c)
                )

    def get_top(self, peer_id: int, days: int = 0):
        with sqlite3.connect(DB_PATH) as conn:
            if days <= 0:
                cur = conn.execute(
                    "SELECT user_id, SUM(msg_count) as msg, SUM(roll_count) as roll "
                    "FROM activity WHERE peer_id = ? GROUP BY user_id "
                    "ORDER BY msg DESC, roll DESC",
                    (peer_id,)
                )
            else:
                days = min(days, 365)
                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                cur = conn.execute(
                    "SELECT user_id, SUM(msg_count) as msg, SUM(roll_count) as roll "
                    "FROM activity WHERE peer_id = ? AND date >= ? GROUP BY user_id "
                    "ORDER BY msg DESC, roll DESC",
                    (peer_id, start_date)
                )
            rows = cur.fetchall()
            result = []
            for user_id, msg, roll in rows:
                name = self.get_name(peer_id, user_id) or f"id{user_id}"
                result.append((name, msg, roll))
            return result

    def remove_left_users(self, peer_id: int, current_member_ids: set[int]):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT DISTINCT user_id FROM users WHERE peer_id = ?",
                (peer_id,)
            )
            db_users = {row[0] for row in cur.fetchall()}
            left = db_users - current_member_ids
            if left:
                placeholders = ','.join('?' * len(left))
                conn.execute(
                    f"DELETE FROM users WHERE peer_id = ? AND user_id IN ({placeholders})",
                    (peer_id, *left)
                )
                conn.execute(
                    f"DELETE FROM activity WHERE peer_id = ? AND user_id IN ({placeholders})",
                    (peer_id, *left)
                )
            return left
