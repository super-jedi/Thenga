import os
import asyncio
from aiohttp import web
import discord
from discord.ext import commands
from dotenv import load_dotenv
import database as db
from utils import format_money

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))

if not TOKEN or TOKEN == "your_bot_token_here":
    raise ValueError("DISCORD_BOT_TOKEN is missing or not set in the .env file.")

# Configure Intents
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# 1. Web Dashboard (For Render Wake-up & Live Status)
# ==========================================
async def handle_ping(request):
    grand_bal = db.get_bank_balance("grandrp")
    libra_bal = db.get_bank_balance("librarp")
    vehicles = db.get_vehicles()
    plantation = db.get_plantation_state()

    html = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Thenga Family RP Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
                .container {{ background: #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); width: 100%; max-width: 600px; }}
                h1 {{ color: #38bdf8; margin-top: 0; margin-bottom: 8px; text-align: center; }}
                .status-badge {{ display: inline-block; background: #16a34a; color: white; padding: 4px 12px; border-radius: 9999px; font-weight: 600; font-size: 13px; margin-bottom: 24px; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
                .card {{ background: #334155; padding: 16px; border-radius: 12px; }}
                .card-title {{ font-size: 13px; color: #94a3b8; text-transform: uppercase; font-weight: 600; margin-bottom: 6px; }}
                .card-value {{ font-size: 20px; font-weight: 700; color: #f1f5f9; }}
                .section {{ border-top: 1px solid #475569; padding-top: 16px; margin-top: 16px; }}
                .section-title {{ font-size: 15px; font-weight: 600; color: #38bdf8; margin-bottom: 8px; }}
                p {{ color: #94a3b8; line-height: 1.5; font-size: 14px; margin: 4px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div style="text-align: center;">
                    <span class="status-badge">● Bot Online & Awake</span>
                    <h1>🥥 Thenga Family RP Hub</h1>
                    <p>Grand RP & Libra RP Management System</p>
                </div>

                <div class="grid" style="margin-top: 24px;">
                    <div class="card">
                        <div class="card-title">Grand RP Family Fund</div>
                        <div class="card-value">{format_money(grand_bal['balance'])}</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Libra RP Family Fund</div>
                        <div class="card-value">{format_money(libra_bal['balance'])}</div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-title">🚗 Family Fleet Status</div>
                    <p>Total Vehicles Registered: <b>{len(vehicles)}</b></p>
                </div>

                <div class="section">
                    <div class="section-title">🍍 Plantation Status</div>
                    <p>Current Status: <b>{plantation.get('status', 'IDLE')}</b> (Crop: Pineapple)</p>
                </div>

                <div class="section" style="text-align: center;">
                    <p style="color: #64748b; font-size: 12px;">Active in Discord • Use /bank, /vehicle, /plantation, /event, /radio</p>
                </div>
            </div>
        </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/wake", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web server listening on port {PORT}")

# ==========================================
# 2. Cog Loader & Discord Events
# ==========================================
COGS = [
    "cogs.bank",
    "cogs.plantation",
    "cogs.vehicles",
    "cogs.moderation",
    "cogs.events",
    "cogs.voice_notes"
]

@bot.event
async def on_ready():
    print("==================================================")
    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s):")
    for g in bot.guilds:
        print(f" - {g.name} (ID: {g.id})")
    print("==================================================")

    # Sync Slash Commands across all servers
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s) successfully.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

async def main():
    # 1. Initialize SQLite Database
    db.init_db()

    # 2. Start Web Server
    await start_web_server()

    # 3. Load all feature Cogs
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"Loaded extension: {cog}")
        except Exception as e:
            print(f"Failed to load extension {cog}: {e}")

    # 4. Start Discord Bot
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
