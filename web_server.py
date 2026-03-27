import os
import aiosqlite
import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()
templates = Jinja2Templates(directory="templates")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/callback")
async def callback(request: Request, code: str):
    async with httpx.AsyncClient() as client:
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        token_resp = await client.post("https://discord.com/api/oauth2/token", data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        access_token = token_resp.json().get("access_token")

        if not access_token:
            return RedirectResponse(url="/")

        user_headers = {"Authorization": f"Bearer {access_token}"}
        guilds_resp = await client.get("https://discord.com/api/users/@me/guilds", headers=user_headers)
        all_guilds = guilds_resp.json()

        admin_guilds = []
        for g in all_guilds:
            permissions = int(g.get('permissions', 0))
            if (permissions & 0x8) == 0x8:
                # Usamos tu número de permisos actualizado
                g['invite_url'] = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=4506898431470678&scope=bot%20applications.commands&guild_id={g['id']}"
                g['dashboard_url'] = f"/dashboard/{g['id']}"
                admin_guilds.append(g)

    return templates.TemplateResponse(request=request, name="guilds_select.html", context={"guilds": admin_guilds})

@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def dashboard_general(request: Request, guild_id: int):
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        resp = await client.get(f"https://discord.com/api/guilds/{guild_id}?with_counts=true", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Bot no encontrado en el servidor.")
        guild_data = resp.json()

    async with aiosqlite.connect("gestion.db") as db:
        async with db.execute("SELECT COUNT(*) FROM niveles WHERE guild_id = ?", (guild_id,)) as c:
            total_ranked = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM warns WHERE guild_id = ?", (guild_id,)) as c:
            total_warns = (await c.fetchone())[0]

    return templates.TemplateResponse(request=request, name="dashboard_general.html", context={
        "guild_id": guild_id, "guild_name": guild_data.get('name'), "guild_icon": guild_data.get('icon'),
        "total_members": guild_data.get('approximate_member_count', 0),
        "total_ranked": total_ranked, "total_warns": total_warns, "active_page": "dashboard"
    })

@app.get("/dashboard/{guild_id}/config", response_class=HTMLResponse)
async def configure_guild_get(request: Request, guild_id: int):
    async with aiosqlite.connect("gestion.db") as db:
        async with db.execute("SELECT welcome_channel_id, auto_role_id FROM config WHERE guild_id = ?", (guild_id,)) as c:
            row = await c.fetchone()
            w_id, r_id = (row[0], row[1]) if row else ("", "")

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://discord.com/api/guilds/{guild_id}", headers={"Authorization": f"Bot {BOT_TOKEN}"})
        guild_name = resp.json().get('name', "Servidor")

    return templates.TemplateResponse(request=request, name="config_modern.html", context={
        "guild_id": guild_id, "guild_name": guild_name, "welcome_channel_id": w_id, "auto_role_id": r_id, "active_page": "config"
    })

@app.post("/dashboard/{guild_id}/config")
async def configure_guild_post(guild_id: int, welcome_channel_id: str = Form(""), auto_role_id: str = Form("")):
    w_id = int(welcome_channel_id) if welcome_channel_id.isdigit() else None
    r_id = int(auto_role_id) if auto_role_id.isdigit() else None
    async with aiosqlite.connect("gestion.db") as db:
        await db.execute("INSERT INTO config (guild_id, welcome_channel_id, auto_role_id) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=excluded.welcome_channel_id, auto_role_id=excluded.auto_role_id", (guild_id, w_id, r_id))
        await db.commit()
    return RedirectResponse(url=f"/dashboard/{guild_id}/config?success=true", status_code=303)