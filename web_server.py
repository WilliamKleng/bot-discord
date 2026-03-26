import os
import aiosqlite
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Cargamos variables de entorno
load_dotenv()

app = FastAPI()

# Configuración de Plantillas
templates = Jinja2Templates(directory="templates")

# Datos del .env
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# URL de Discord para iniciar el login
DISCORD_AUTH_URL = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Página de inicio con el botón de Login"""
    return f"""
    <html>
        <body style="font-family: Arial; text-align: center; margin-top: 50px; background-color: #2c2f33; color: white;">
            <h1>Panel de Gestión SaaS</h1>
            <p>Conectá tu servidor de Discord para empezar.</p>
            <br>
            <a href="{DISCORD_AUTH_URL}" style="padding: 15px 25px; background: #5865F2; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Login con Discord
            </a>
        </body>
    </html>
    """

@app.get("/callback")
async def callback(request: Request, code: str):
    """Maneja el login, obtiene el token y filtra los servidores donde el usuario es Admin"""
    async with httpx.AsyncClient() as client:
        # 1. Obtener Token
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_resp = await client.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
        token_json = token_resp.json()
        access_token = token_json.get("access_token")

        if not access_token:
            # Si el código expiró o es inválido, redirigimos al inicio
            return RedirectResponse(url="/")

        # 2. Pedir servidores del usuario
        user_headers = {"Authorization": f"Bearer {access_token}"}
        guilds_resp = await client.get("https://discord.com/api/users/@me/guilds", headers=user_headers)
        all_guilds = guilds_resp.json()

        # 3. Filtrar administradores
        admin_guilds = []
        for g in all_guilds:
            permissions = int(g.get('permissions', 0))
            if (permissions & 0x8) == 0x8:
                g['invite_url'] = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands&guild_id={g['id']}"
                admin_guilds.append(g)

    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={"guilds": admin_guilds}
    )

@app.get("/config/{guild_id}", response_class=HTMLResponse)
async def configure_guild_get(request: Request, guild_id: int):
    """Muestra el formulario pre-cargado con los datos actuales de la DB"""
    welcome_channel_id = ""
    auto_role_id = ""

    async with aiosqlite.connect("gestion.db") as db:
        async with db.execute("SELECT welcome_channel_id, auto_role_id FROM config WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                welcome_channel_id = row[0] if row[0] else ""
                auto_role_id = row[1] if row[1] else ""

    return templates.TemplateResponse(
        request=request, 
        name="config.html", 
        context={
            "guild_id": guild_id,
            "welcome_channel_id": welcome_channel_id,
            "auto_role_id": auto_role_id
        }
    )

@app.post("/config/{guild_id}", response_class=HTMLResponse)
async def configure_guild_post(
    request: Request, 
    guild_id: int, 
    welcome_channel_id: str = Form(""), 
    auto_role_id: str = Form("")
):
    """Recibe los datos del formulario y los guarda/actualiza en la base de datos"""
    w_id = int(welcome_channel_id) if welcome_channel_id.isdigit() else None
    r_id = int(auto_role_id) if auto_role_id.isdigit() else None

    async with aiosqlite.connect("gestion.db") as db:
        await db.execute("""
            INSERT INTO config (guild_id, welcome_channel_id, auto_role_id) 
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET 
            welcome_channel_id=excluded.welcome_channel_id, 
            auto_role_id=excluded.auto_role_id
        """, (guild_id, w_id, r_id))
        await db.commit()

    return templates.TemplateResponse(
        request=request, 
        name="config.html", 
        context={
            "guild_id": guild_id,
            "welcome_channel_id": welcome_channel_id,
            "auto_role_id": auto_role_id,
            "mensaje": "✅ ¡Configuración guardada exitosamente!"
        }
    )

if __name__ == "__main__":
    import uvicorn
    print("🌍 Servidor web iniciado en http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)