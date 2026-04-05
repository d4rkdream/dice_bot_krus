import aiosqlite
import os

DB_PATH = "names.db"

class Database:
    def __init__(self):
        self.conn = None

    async def _ensure_connection(self):
        if self.conn is None:
            self.conn = await aiosqlite.connect(DB_PATH)
            await self.conn.execute('''
                CREATE TABLE IF NOT EXISTS user_names (
                    peer_id INTEGER,
                    user_id INTEGER,
                    name TEXT,
                    PRIMARY KEY (peer_id, user_id)
                )
            ''')
            await self.conn.commit()

    async def get_name(self, peer_id: int, user_id: int) -> str | None:
        await self._ensure_connection()
        cursor = await self.conn.execute(
            "SELECT name FROM user_names WHERE peer_id = ? AND user_id = ?",
            (peer_id, user_id)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def set_name(self, peer_id: int, user_id: int, name: str):
        await self._ensure_connection()
        await self.conn.execute(
            "INSERT OR REPLACE INTO user_names (peer_id, user_id, name) VALUES (?, ?, ?)",
            (peer_id, user_id, name)
        )
        await self.conn.commit()
