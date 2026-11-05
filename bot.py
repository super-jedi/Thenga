import os
import io
import asyncio
import aiohttp
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))

if not TOKEN or TOKEN == "your_bot_token_here":
    raise ValueError("DISCORD_BOT_TOKEN is missing or not set in the environment.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# 1. Tiny Web Server to Wake Up Render
# ==========================================
async def handle_ping(request):
    return web.Response(
        text="""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Thenga Bot Status</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
                    .card { background: #1e293b; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); text-align: center; max-width: 450px; }
                    h1 { color: #38bdf8; margin-bottom: 12px; }
                    .badge { display: inline-block; background: #16a34a; color: white; padding: 6px 14px; border-radius: 9999px; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
                    p { color: #94a3b8; line-height: 1.6; font-size: 15px; }
                    code { background: #334155; color: #e2e8f0; padding: 3px 6px; border-radius: 4px; font-size: 14px; }
                </style>
            </head>
            <body>
                <div class="card">
                    <span class="badge">● Online & Awake</span>
                    <h1>🤖 Thenga Bot</h1>
                    <p>The bot is currently connected to Discord and will stay active for the next 15 minutes.</p>
                    <p>Go to your Discord channel and run your commands:<br><br><code>/forward_last</code> or <code>/forward_range</code></p>
                </div>
            </body>
        </html>
        """,
        content_type="text/html"
    )

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
# 2. Discord Forwarding Logic
# ==========================================
@bot.event
async def on_ready():
    print(f"==================================================")
    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print(f"==================================================")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

async def resolve_target_webhook(target_input: str, session: aiohttp.ClientSession) -> discord.Webhook:
    target_clean = target_input.strip()
    if target_clean.startswith("http://") or target_clean.startswith("https://"):
        return discord.Webhook.from_url(target_clean, session=session)
    
    channel = await bot.fetch_channel(int(target_clean))
    if not isinstance(channel, discord.TextChannel):
        raise ValueError(f"Channel {target_clean} is not a standard text channel.")
    
    webhooks = await channel.webhooks()
    webhook = next((w for w in webhooks if w.name == "ForwarderBot"), None)
    if not webhook:
        webhook = await channel.create_webhook(name="ForwarderBot")
    return webhook

async def dispatch_forward(messages: list[discord.Message], target_input: str, interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        try:
            webhook = await resolve_target_webhook(target_input, session)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reach target destination: `{e}`")
            return

        total = len(messages)
        success = 0

        for msg in messages:
            if msg.is_system():
                continue

            files = []
            for att in msg.attachments:
                if att.size <= 25 * 1024 * 1024:
                    try:
                        async with session.get(att.url) as resp:
                            if resp.status == 200:
                                files.append(discord.File(io.BytesIO(await resp.read()), filename=att.filename))
                    except Exception:
                        pass

            content = msg.content if msg.content else None
            avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else None

            if not content and not files and not msg.embeds:
                continue

            try:
                await webhook.send(
                    content=content,
                    username=msg.author.display_name,
                    avatar_url=avatar_url,
                    embeds=msg.embeds,
                    files=files
                )
                success += 1
            except Exception as e:
                print(f"Error sending message: {e}")

            await asyncio.sleep(1.2)

        await interaction.followup.send(f"✅ Forwarding complete! Transferred **{success}/{total}** messages.")

@bot.tree.command(name="forward_last", description="Forward last N messages from a channel.")
@app_commands.describe(
    source_channel_id="Channel ID to copy from",
    target="Destination Channel ID OR Webhook URL to copy to",
    count="Number of messages (1-100)"
)
async def forward_last(interaction: discord.Interaction, source_channel_id: str, target: str, count: int = 10):
    await interaction.response.defer(ephemeral=True)
    if count < 1 or count > 100:
        await interaction.followup.send("❌ Count must be between 1 and 100.")
        return

    try:
        source = await bot.fetch_channel(int(source_channel_id.strip()))
    except Exception as e:
        await interaction.followup.send(f"❌ Could not access source channel: `{e}`")
        return

    raw = [msg async for msg in source.history(limit=count)]
    messages = list(reversed(raw))

    if not messages:
        await interaction.followup.send("⚠️ No messages found in source channel.")
        return

    await interaction.followup.send(f"⏳ Found {len(messages)} messages. Forwarding now...")
    await dispatch_forward(messages, target, interaction)

@bot.tree.command(name="forward_range", description="Forward messages between two message IDs.")
@app_commands.describe(
    source_channel_id="Channel ID to copy from",
    target="Destination Channel ID OR Webhook URL to copy to",
    start_message_id="First message ID",
    end_message_id="Last message ID"
)
async def forward_range(interaction: discord.Interaction, source_channel_id: str, target: str, start_message_id: str, end_message_id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        source = await bot.fetch_channel(int(source_channel_id.strip()))
        start_id = int(start_message_id.strip())
        end_id = int(end_message_id.strip())
    except Exception as e:
        await interaction.followup.send(f"❌ Invalid inputs: `{e}`")
        return

    if start_id > end_id:
        start_id, end_id = end_id, start_id

    try:
        start_msg = await source_channel.fetch_message(start_id)
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching start message: `{e}`")
        return

    messages = [start_msg]
    async for msg in source.history(after=discord.Object(id=start_id), oldest_first=True, limit=200):
        messages.append(msg)
        if msg.id == end_id:
            break

    await interaction.followup.send(f"⏳ Found {len(messages)} messages in range. Forwarding now...")
    await dispatch_forward(messages, target, interaction)

# ==========================================
# 3. Main Runner
# ==========================================
async def main():
    await start_web_server()
    await bot.start(TOKEN)

if __name__ == "__main__":
    print("Starting bot and web server...")
    asyncio.run(main())
