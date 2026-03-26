import aiosqlite
import os

DB_PATH = "gestion.db"
MIGRATIONS_TABLE = "migrations"

MIGRATIONS = [
    # (id, SQL)
    (1, '''CREATE TABLE IF NOT EXISTS niveles 
        (guild_id INTEGER, user_id INTEGER, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, PRIMARY KEY (guild_id, user_id))'''),
    (2, '''CREATE TABLE IF NOT EXISTS warns 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, reason TEXT, moderator_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)'''),
    (3, '''CREATE TABLE IF NOT EXISTS config (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                auto_role_id INTEGER
            )'''),
]

async def run_migrations():
    """
    Ejecuta migraciones pendientes en la base de datos.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f'''CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (id INTEGER PRIMARY KEY)''')
        await db.commit()
        for mig_id, mig_sql in MIGRATIONS:
            async with db.execute(f"SELECT 1 FROM {MIGRATIONS_TABLE} WHERE id = ?", (mig_id,)) as cursor:
                exists = await cursor.fetchone()
            if not exists:
                await db.execute(mig_sql)
                await db.execute(f"INSERT INTO {MIGRATIONS_TABLE} (id) VALUES (?)", (mig_id,))
                await db.commit()

async def init_db():
    await run_migrations()