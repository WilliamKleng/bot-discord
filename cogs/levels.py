

import logging
import random
import time
from typing import Optional

import discord
from discord.ext import commands
import aiosqlite

logger = logging.getLogger("bot.levels")
logger.setLevel(logging.INFO)

class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        """
        Inicializa el sistema de niveles.
        :param bot: Instancia del bot de Discord.
        """
        self.bot: commands.Bot = bot
        self.cooldowns = {}  # type: ignore[var-annotated]

    async def _get_user_level_data(self, guild_id: int, user_id: int) -> Optional[tuple[int, int]]:
        """
        Obtiene el XP y nivel de un usuario en un servidor.
        """
        async with aiosqlite.connect("gestion.db") as db:
            async with db.execute(
                "SELECT xp, level FROM niveles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                return await cursor.fetchone()

    async def _insert_new_user(self, guild_id: int, user_id: int) -> None:
        """
        Inserta un nuevo usuario en la tabla de niveles.
        """
        async with aiosqlite.connect("gestion.db") as db:
            await db.execute(
                "INSERT INTO niveles (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, 20, 1)
            )
            await db.commit()

    async def _update_user_level(self, guild_id: int, user_id: int, xp: int, level: int) -> None:
        """
        Actualiza el XP y nivel de un usuario en la base de datos.
        """
        async with aiosqlite.connect("gestion.db") as db:
            await db.execute(
                "UPDATE niveles SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?",
                (xp, level, guild_id, user_id)
            )
            await db.commit()

    async def _get_auto_role_id(self, guild_id: int) -> Optional[int]:
        """
        Obtiene el ID del rol automático configurado para el servidor.
        """
        async with aiosqlite.connect("gestion.db") as db:
            async with db.execute(
                "SELECT auto_role_id FROM config WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    try:
                        return int(row[0])
                    except Exception as e:
                        logger.error(f"Error al convertir auto_role_id: {e}")
                return None

    async def _assign_auto_role(self, member: discord.Member, role_id: int, channel: discord.TextChannel, guild_id: int) -> None:
        """
        Asigna el rol automático al usuario si es posible.
        """
        rol = member.guild.get_role(role_id)
        if rol:
            try:
                await member.add_roles(rol)
                await channel.send(f"🛡️ {member.mention} recibió un nuevo rol por actividad.")
            except discord.Forbidden:
                await channel.send(f"⚠️ {member.mention}, no tengo permisos suficientes para asignarte el rol configurado. Pide a un admin que ajuste los permisos del bot.")
                logger.warning(f"Faltan permisos para dar el rol {role_id} en {guild_id}")
            except Exception as e:
                await channel.send(f"❌ {member.mention}, ocurrió un error inesperado al asignar el rol. Contacta a un admin.")
                logger.error(f"Error inesperado al asignar rol: {e}")
        else:
            await channel.send(f"⚠️ {member.mention}, el rol configurado para nivel 5 no existe en este servidor. Pide a un admin que lo configure correctamente.")
            logger.warning(f"Rol con ID {role_id} no encontrado en el servidor {guild_id}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Listener para el evento de mensaje. Gestiona XP, niveles y auto-roles.
        :param message: Mensaje recibido en Discord.
        """
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        current_time = time.time()

        # Cooldown de 60 segundos para evitar spam de XP
        if user_id not in self.cooldowns or (current_time - self.cooldowns[user_id]) > 60:
            try:
                row = await self._get_user_level_data(guild_id, user_id)
                if row is None:
                    await self._insert_new_user(guild_id, user_id)
                else:
                    xp, level = row
                    nuevo_xp = xp + random.randint(15, 25)
                    proximo_nivel_xp = level * 100

                    if nuevo_xp >= proximo_nivel_xp:
                        level += 1
                        await message.channel.send(f"🎊 ¡{message.author.mention} subió al **Nivel {level}**!")

                        if level == 5:
                            role_id = await self._get_auto_role_id(guild_id)
                            if role_id:
                                await self._assign_auto_role(message.author, role_id, message.channel, guild_id)

                    await self._update_user_level(guild_id, user_id, nuevo_xp, level)
                self.cooldowns[user_id] = current_time
            except Exception as e:
                logger.error(f"Error en el sistema de niveles: {e}")

    @commands.command()
    async def rank(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """
        Muestra el nivel y XP de un usuario.
        :param ctx: Contexto del comando.
        :param member: Miembro a consultar (opcional).
        """
        member = member or ctx.author
        async with aiosqlite.connect("gestion.db") as db:
            async with db.execute(
                "SELECT xp, level FROM niveles WHERE guild_id = ? AND user_id = ?", 
                (ctx.guild.id, member.id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    xp, level = row
                    embed = discord.Embed(title=f"Estadísticas de {member.name}", color=0x3498db)
                    embed.add_field(name="Nivel", value=level, inline=True)
                    embed.add_field(name="XP", value=f"{xp}/{level*100}", inline=True)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Este usuario aún no tiene actividad registrada.")

    @commands.command()
    async def leaderboard(self, ctx: commands.Context, top: int = 10) -> None:
        """
        Muestra el top de usuarios con más XP en el servidor.
        :param ctx: Contexto del comando.
        :param top: Número de posiciones a mostrar (máx 25).
        """
        if top < 1 or top > 25:
            await ctx.send("El número de posiciones debe estar entre 1 y 25.")
            return
        async with aiosqlite.connect("gestion.db") as db:
            async with db.execute(
                "SELECT user_id, xp, level FROM niveles WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?",
                (ctx.guild.id, top)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No hay datos de niveles para este servidor.")
            return
        embed = discord.Embed(title=f"🏆 Leaderboard de {ctx.guild.name}", color=0xf1c40f)
        for idx, (user_id, xp, level) in enumerate(rows, start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"Usuario {user_id}"
            embed.add_field(
                name=f"#{idx} {name}",
                value=f"Nivel: {level} | XP: {xp}",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def set_welcome_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """
        Configura el canal de bienvenida para el servidor.
        :param ctx: Contexto del comando.
        :param channel: Canal de texto a configurar.
        """
        async with aiosqlite.connect("gestion.db") as db:
            await db.execute(
                "INSERT INTO config (guild_id, welcome_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=excluded.welcome_channel_id",
                (ctx.guild.id, channel.id)
            )
            await db.commit()
        await ctx.send(f"✅ Canal de bienvenida configurado: {channel.mention}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def set_auto_role(self, ctx: commands.Context, role: discord.Role) -> None:
        """
        Configura el rol automático para nivel 5 en el servidor.
        :param ctx: Contexto del comando.
        :param role: Rol a configurar como auto-rol.
        """
        async with aiosqlite.connect("gestion.db") as db:
            await db.execute(
                "INSERT INTO config (guild_id, auto_role_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET auto_role_id=excluded.auto_role_id",
                (ctx.guild.id, role.id)
            )
            await db.commit()
        await ctx.send(f"✅ Rol automático configurado: {role.mention}")


async def setup(bot: commands.Bot) -> None:
    """
    Carga el cog de Levels en el bot.
    :param bot: Instancia del bot de Discord.
    """
    await bot.add_cog(Levels(bot))