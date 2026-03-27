import os
import aiosqlite
import httpx
from typing import Optional
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Configuración de Archivos Estáticos y Plantillas
if not os.path.exists("static/css"):
    os.makedirs("static/css", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Variables de Entorno
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds"
    return templates.TemplateResponse(request=request, name="index.html", context={"discord_auth_url": auth_url})

@app.get("/callback")
async def callback(request: Request, code: Optional[str] = None):
    if not code:
        return RedirectResponse(url="/")

    async with httpx.AsyncClient() as client:
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        token_resp = await client.post("https://discord.com/api/oauth2/token", data=data)
        access_token = token_resp.json().get("access_token")

        if not access_token:
            return RedirectResponse(url="/")

        user_headers = {"Authorization": f"Bearer {access_token}"}
        guilds_resp = await client.get("https://discord.com/api/users/@me/guilds", headers=user_headers)
        admin_guilds = [g for g in guilds_resp.json() if (int(g.get('permissions', 0)) & 0x8) == 0x8]

        for g in admin_guilds:
            g['invite_url'] = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=4506898431470678&scope=bot%20applications.commands&guild_id={g['id']}"
            g['dashboard_url'] = f"/dashboard/{g['id']}"

    return templates.TemplateResponse(request=request, name="guilds_select.html", context={"guilds": admin_guilds})


@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def dashboard(request: Request, guild_id: int):
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        resp = await client.get(f"https://discord.com/api/guilds/{guild_id}?with_counts=true", headers=headers)
        if resp.status_code != 200:
            return RedirectResponse(url="/callback")
        guild_data = resp.json()

        # Para obtener nombres y avatares reales de usuarios y moderadores
        async def get_user(user_id):
            user_resp = await client.get(f"https://discord.com/api/users/{user_id}", headers=headers)
            if user_resp.status_code == 200:
                u = user_resp.json()
                avatar_url = f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.png" if u.get('avatar') else "https://cdn.discordapp.com/embed/avatars/0.png"
                return {"username": u['username'] + (f"#{u['discriminator']}" if u.get('discriminator') else ''), "avatar_url": avatar_url}
            else:
                return {"username": f"Usuario {user_id}", "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"}

    async with aiosqlite.connect("gestion.db") as db:
        # Usuarios en ranking
        async with db.execute("SELECT COUNT(*) FROM niveles WHERE guild_id = ?", (guild_id,)) as cursor:
            usuarios_ranking = (await cursor.fetchone())[0]
        # XP total acumulado
        async with db.execute("SELECT COALESCE(SUM(xp), 0) FROM niveles WHERE guild_id = ?", (guild_id,)) as cursor:
            xp_total = (await cursor.fetchone())[0]
        # Total warns
        async with db.execute("SELECT COUNT(*) FROM warns WHERE guild_id = ?", (guild_id,)) as cursor:
            total_warns = (await cursor.fetchone())[0]
        # Últimos 5 warns
        ultimos_warns = []
        async with db.execute("""
            SELECT w.user_id, w.reason, w.moderator_id, w.timestamp
            FROM warns w
            WHERE w.guild_id = ?
            ORDER BY w.timestamp DESC
            LIMIT 5
        """, (guild_id,)) as cursor:
            async for row in cursor:
                user_id, razon, mod_id, fecha = row
                user_info = await get_user(user_id)
                mod_info = await get_user(mod_id)
                ultimos_warns.append({
                    "user_id": user_id,
                    "username": user_info["username"],
                    "user_avatar": user_info["avatar_url"],
                    "razon": razon,
                    "moderador": mod_info["username"],
                    "moderador_avatar": mod_info["avatar_url"],
                    "fecha": fecha
                })
        # Top 5 usuarios por nivel/xp
        top_usuarios = []
        async with db.execute("""
            SELECT user_id, xp, level FROM niveles WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 5
        """, (guild_id,)) as cursor:
            async for row in cursor:
                user_id, xp, nivel = row
                user_info = await get_user(user_id)
                top_usuarios.append({
                    "user_id": user_id,
                    "username": user_info["username"],
                    "avatar_url": user_info["avatar_url"],
                    "nivel": nivel,
                    "xp": xp
                })
        # Estado de configuración
        async with db.execute("SELECT welcome_channel_id, auto_role_id FROM config WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            welcome_channel_id = row[0] if row else None
            auto_role_id = row[1] if row else None

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "guild_id": guild_id,
        "guild_name": guild_data.get('name'),
        "total_miembros": guild_data.get('approximate_member_count', 0),
        "usuarios_ranking": usuarios_ranking,
        "xp_total": xp_total,
        "total_warns": total_warns,
        "ultimos_warns": ultimos_warns,
        "top_usuarios": top_usuarios,
        "welcome_channel_id": welcome_channel_id,
        "auto_role_id": auto_role_id,
        # Placeholder para gráfico de actividad semanal
        "actividad_semanal": []
    })