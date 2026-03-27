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

if not os.path.exists("static/css"):
    os.makedirs("static/css", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def get_user_info(client: httpx.AsyncClient, user_id: int) -> dict:
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    resp = await client.get(f"https://discord.com/api/users/{user_id}", headers=headers)
    if resp.status_code == 200:
        u = resp.json()
        avatar_url = (
            f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.png"
            if u.get("avatar")
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        )
        discriminator = u.get("discriminator", "0")
        username = u["username"] if discriminator == "0" else f"{u['username']}#{discriminator}"
        return {"username": username, "avatar_url": avatar_url}
    return {"username": f"Usuario {user_id}", "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"}


# ── RUTAS PÚBLICAS ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"discord_auth_url": auth_url}
    )


@app.get("/callback")
async def callback(request: Request, code: Optional[str] = None):
    if not code:
        return RedirectResponse(url="/")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            }
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return RedirectResponse(url="/")

        headers = {"Authorization": f"Bearer {access_token}"}
        guilds_resp = await client.get("https://discord.com/api/users/@me/guilds", headers=headers)
        all_guilds = guilds_resp.json()

        # Solo servidores donde el usuario es admin
        admin_guilds = [
            g for g in all_guilds
            if isinstance(g.get("permissions"), (int, str))
            and (int(g.get("permissions", 0)) & 0x8) == 0x8
        ]

        for g in admin_guilds:
            g["invite_url"] = (
                f"https://discord.com/api/oauth2/authorize"
                f"?client_id={CLIENT_ID}"
                f"&permissions=8"
                f"&scope=bot"
                f"&guild_id={g['id']}"
            )
            g["dashboard_url"] = f"/dashboard/{g['id']}"

    return templates.TemplateResponse(
        request=request,
        name="guilds_select.html",
        context={"guilds": admin_guilds}
    )


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def dashboard(request: Request, guild_id: int):
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        guild_resp = await client.get(
            f"https://discord.com/api/guilds/{guild_id}?with_counts=true",
            headers=headers
        )
        if guild_resp.status_code != 200:
            return RedirectResponse(url="/callback")
        guild_data = guild_resp.json()

        async with aiosqlite.connect("gestion.db") as db:
            # Usuarios en ranking
            async with db.execute(
                "SELECT COUNT(*) FROM niveles WHERE guild_id = ?", (guild_id,)
            ) as cur:
                usuarios_ranking = (await cur.fetchone())[0]

            # XP total
            async with db.execute(
                "SELECT COALESCE(SUM(xp), 0) FROM niveles WHERE guild_id = ?", (guild_id,)
            ) as cur:
                xp_total = (await cur.fetchone())[0]

            # Total warns
            async with db.execute(
                "SELECT COUNT(*) FROM warns WHERE guild_id = ?", (guild_id,)
            ) as cur:
                total_warns = (await cur.fetchone())[0]

            # Últimos 5 warns
            ultimos_warns = []
            async with db.execute(
                """SELECT user_id, reason, moderator_id, timestamp
                   FROM warns WHERE guild_id = ?
                   ORDER BY timestamp DESC LIMIT 5""",
                (guild_id,)
            ) as cur:
                async for row in cur:
                    user_id, razon, mod_id, fecha = row
                    user_info = await get_user_info(client, user_id)
                    ultimos_warns.append({
                        "username": user_info["username"],
                        "user_avatar": user_info["avatar_url"],
                        "razon": razon,
                        "fecha": fecha,
                    })

            # Top 5 usuarios
            top_usuarios = []
            
            async with db.execute(
                """SELECT user_id, xp, level FROM niveles
                   WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 5""",
                (guild_id,)
            ) as cur:
                async for row in cur:
                    user_id, xp, nivel = row
                    user_info = await get_user_info(client, user_id)
                    top_usuarios.append({
                        "username": user_info["username"],
                        "avatar_url": user_info["avatar_url"],
                        "nivel": nivel,
                        "xp": xp,       
                    })
                
            if top_usuarios:
                max_xp = top_usuarios[0]["xp"] if top_usuarios[0]["xp"] > 0 else 1
                for u in top_usuarios:
                    u["pct"] = min(int(u["xp"] / max_xp * 100), 100)

            # Config
            async with db.execute(
                "SELECT welcome_channel_id, auto_role_id FROM config WHERE guild_id = ?",
                (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                welcome_channel_id = row[0] if row else None
                auto_role_id = row[1] if row else None

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "guild_id": guild_id,
            "guild_name": guild_data.get("name", "Servidor"),
            "total_miembros": guild_data.get("approximate_member_count", 0),
            "usuarios_ranking": usuarios_ranking,
            "xp_total": xp_total,
            "total_warns": total_warns,
            "ultimos_warns": ultimos_warns,
            "top_usuarios": top_usuarios,
            "welcome_channel_id": welcome_channel_id,
            "auto_role_id": auto_role_id,
        }
    )


# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────

@app.get("/dashboard/{guild_id}/config", response_class=HTMLResponse)
async def config_get(request: Request, guild_id: int):
    async with aiosqlite.connect("gestion.db") as db:
        async with db.execute(
            "SELECT welcome_channel_id, auto_role_id FROM config WHERE guild_id = ?",
            (guild_id,)
        ) as cur:
            row = await cur.fetchone()
            welcome_channel_id = row[0] if row else None
            auto_role_id = row[1] if row else None

    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={
            "guild_id": guild_id,
            "welcome_channel_id": welcome_channel_id,
            "auto_role_id": auto_role_id,
            "mensaje": None,
        }
    )


@app.post("/config/{guild_id}", response_class=HTMLResponse)
async def config_post(
    request: Request,
    guild_id: int,
    welcome_channel_id: Optional[str] = Form(None),
    auto_role_id: Optional[str] = Form(None),
):
    wc = int(welcome_channel_id) if welcome_channel_id and welcome_channel_id.strip() else None
    ar = int(auto_role_id) if auto_role_id and auto_role_id.strip() else None

    async with aiosqlite.connect("gestion.db") as db:
        await db.execute(
            """INSERT INTO config (guild_id, welcome_channel_id, auto_role_id)
               VALUES (?, ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET
               welcome_channel_id = excluded.welcome_channel_id,
               auto_role_id = excluded.auto_role_id""",
            (guild_id, wc, ar)
        )
        await db.commit()

    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={
            "guild_id": guild_id,
            "welcome_channel_id": wc,
            "auto_role_id": ar,
            "mensaje": "Configuración guardada correctamente.",
        }
    )