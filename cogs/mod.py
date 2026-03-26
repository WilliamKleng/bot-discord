import discord
from discord.ext import commands
import aiosqlite

class Moderacion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, cantidad: int):
        await ctx.channel.purge(limit=cantidad + 1)
        await ctx.send(f"🗑️ Eliminados {cantidad} mensajes.", delete_after=5)

    # Acá irían los comandos de warn, ban, etc. que ya hicimos

async def setup(bot):
    await bot.add_cog(Moderacion(bot))