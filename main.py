import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv # <--- Importamos la librería
from database import init_db

# Cargamos las variables del archivo .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN') # <--- Traemos el token de forma segura

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        await init_db()
        # Cargamos los módulos (Cogs)
        if os.path.exists('./cogs'):
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f'📦 Módulo cargado: {filename}')

bot = MyBot()

async def main():
    if not TOKEN:
        print("❌ Error: No se encontró el DISCORD_TOKEN en el archivo .env")
        return
        
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Bot apagado manualmente.")