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
async def dashboard_general(request: Request, guild_id: int):
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        resp = await client.get(f"https://discord.com/api/guilds/{guild_id}?with_counts=true", headers=headers)
        if resp.status_code != 200:
            return RedirectResponse(url="/callback")
        guild_data = resp.json()

    async with aiosqlite.connect("gestion.db") as db:
        async with db.execute("SELECT COUNT(*) FROM niveles WHERE guild_id = ?", (guild_id,)) as cursor:
            total_ranked = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM warns WHERE guild_id = ?", (guild_id,)) as cursor:
            total_warns = (await cursor.fetchone())[0]

    return templates.TemplateResponse(request=request, name="dashboard_general.html", context={
        "guild_id": guild_id,
        "guild_name": guild_data.get('name'),
        "total_members": guild_data.get('approximate_member_count', 0),
        "total_ranked": total_ranked,
        "total_warns": total_warns
    })