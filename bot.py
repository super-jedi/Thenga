import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from aiohttp import web
import discord
from discord.ext import commands

import database as db
from web_server import create_web_app

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))

if not TOKEN or TOKEN == "your_bot_token_here":
    raise ValueError("DISCORD_BOT_TOKEN is missing or not set in the .env file.")

# Configure Intents
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

COGS = [
    "cogs.grand",
    "cogs.libra",
    "cogs.moderation",
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

async def start_web_server():
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web Dashboard & APIs listening on port {PORT}")

async def main():
    # 1. Initialize SQLite Database
    db.init_db()

    # 2. Start Web Dashboard
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
