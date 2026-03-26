import discord
from discord.ext import commands
import aiosqlite

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Consulta a la base de datos para obtener el canal de este servidor específico
        async with aiosqlite.connect("gestion.db") as db:
            async with db.execute("SELECT welcome_channel_id FROM config WHERE guild_id = ?", (member.guild.id,)) as cursor:
                row = await cursor.fetchone()
        
        # Si el servidor no fue configurado en el panel web o no asignó canal, se ignora
        if not row or not row[0]:
            return
            
        channel_id = row[0]
        channel = member.guild.get_channel(channel_id)
        
        if channel:
            embed = discord.Embed(
                title=f"¡Bienvenido/a {member.name}!",
                description=f"Gracias por unirte a **{member.guild.name}**.",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Welcome(bot))