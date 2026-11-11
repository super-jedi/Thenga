import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
from typing import Optional
from utils import detect_server
import database as db

class EventsCog(commands.Cog, name="RP Events"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    event_group = app_commands.Group(name="event", description="Manage Libra RP & Grand RP Event Alerts")

    @event_group.command(name="add", description="Add an automated event schedule/alert.")
    @app_commands.describe(
        name="Name of the event (e.g. Aircraft Carrier, Submarine, Ghost Hunt, Bizwar)",
        time_utc="Event time in 24-hr UTC format (e.g. 18:30 or 14:00)",
        role_to_ping="Role to mention (e.g. @Event Radio)",
        channel="Channel to send the alert in (e.g. #announcements-and-codes or #event-radio)",
        description="Notes (e.g. Bring full armor, meet at family warehouse)",
        server="Which RP server"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Libra RP", value="librarp"),
        app_commands.Choice(name="Grand RP", value="grandrp")
    ])
    async def add_event(
        self,
        interaction: discord.Interaction,
        name: str,
        time_utc: str,
        channel: discord.TextChannel,
        role_to_ping: Optional[discord.Role] = None,
        description: str = "Family gathering for event",
        server: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        # Validate time format
        try:
            parts = time_utc.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError()
            formatted_time = f"{h:02d}:{m:02d}"
        except Exception:
            await interaction.followup.send("❌ Invalid time format! Please provide time as `HH:MM` in 24-hour UTC, e.g. `16:30` or `08:00`.")
            return

        role_id = role_to_ping.id if role_to_ping else None
        db.add_event(
            server=target_server,
            name=name.strip(),
            time_utc=formatted_time,
            description=description.strip(),
            role_id=role_id,
            channel_id=channel.id
        )

        role_mention = role_to_ping.mention if role_to_ping else "None"
        embed = discord.Embed(
            title=f"📅 Event Schedule Added — {target_server.upper()}",
            color=discord.Color.purple(),
            description=f"**{name}** has been scheduled for daily alerts."
        )
        embed.add_field(name="⏰ Time (UTC)", value=f"`{formatted_time} UTC`", inline=True)
        embed.add_field(name="📢 Channel", value=channel.mention, inline=True)
        embed.add_field(name="🔔 Role Ping", value=role_mention, inline=True)
        embed.add_field(name="📝 Details", value=description, inline=False)
        embed.set_footer(text="Alerts will automatically ping 10 minutes before and at event time.")

        await interaction.followup.send(embed=embed)

    @event_group.command(name="list", description="List all scheduled daily event alerts.")
    @app_commands.describe(server="Filter by server")
    @app_commands.choices(server=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Libra RP", value="librarp"),
        app_commands.Choice(name="Grand RP", value="grandrp")
    ])
    async def list_events(self, interaction: discord.Interaction, server: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        srv = server.value if server and server.value != "all" else None
        events = db.get_events(srv)

        if not events:
            await interaction.followup.send("📅 No events currently scheduled. Add one with `/event add`!")
            return

        embed = discord.Embed(
            title="🎮 Scheduled Family Events",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )

        for e in events:
            role_txt = f"<@&{e['role_id']}>" if e.get("role_id") else "No role ping"
            ch_txt = f"<#{e['channel_id']}>" if e.get("channel_id") else "Default"
            val = f"⏰ **{e['time_utc']} UTC** | 📢 {ch_txt} | 🔔 {role_txt}\n*{e['description']}*"
            embed.add_field(name=f"ID #{e['id']} — [{e['server'].upper()}] {e['name']}", value=val, inline=False)

        embed.set_footer(text="Use /event remove [id] to delete an event.")
        await interaction.followup.send(embed=embed)

    @event_group.command(name="remove", description="Delete an event schedule.")
    @app_commands.describe(event_id="ID of the event to delete")
    async def remove_event(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer()
        success = db.remove_event(event_id)
        if success:
            await interaction.followup.send(f"🗑️ Removed event ID `#{event_id}`.")
        else:
            await interaction.followup.send(f"❌ Event ID `#{event_id}` not found.")

    @event_group.command(name="test", description="Send a test alert for a scheduled event.")
    @app_commands.describe(event_id="ID of the event to test")
    async def test_alert(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        events = db.get_events()
        event = next((e for e in events if e["id"] == event_id), None)
        if not event:
            await interaction.followup.send(f"❌ Event `#{event_id}` not found.")
            return

        channel = self.bot.get_channel(event["channel_id"])
        if not channel:
            channel = interaction.channel

        role_ping = f"<@&{event['role_id']}> " if event.get("role_id") else ""
        embed = discord.Embed(
            title=f"🚨 [TEST ALERT] {event['name'].upper()} IN 10 MINUTES!",
            color=discord.Color.red(),
            description=f"{event['description']}\n\n**Server:** {event['server'].upper()}\n**Gear up and gather at Family House!**",
            timestamp=discord.utils.utcnow()
        )
        await channel.send(content=role_ping, embed=embed)
        await interaction.followup.send("✅ Test alert sent!")

    # Background task to check events every minute
    @tasks.loop(seconds=60)
    async def check_events(self):
        try:
            now_utc = datetime.now(timezone.utc)
            cur_time_str = now_utc.strftime("%H:%M")
            cur_date_str = now_utc.strftime("%Y-%m-%d")

            events = db.get_events()
            conn = db.get_connection()

            for e in events:
                e_time = e["time_utc"] # e.g. "18:30"
                # Check if matches current time and not already triggered today
                trigger_key = f"{e['id']}_{cur_date_str}_{cur_time_str}"
                if cur_time_str == e_time and e.get("last_triggered_date") != trigger_key:
                    channel = self.bot.get_channel(e["channel_id"])
                    if channel:
                        role_ping = f"<@&{e['role_id']}> " if e.get("role_id") else ""
                        embed = discord.Embed(
                            title=f"⚔️ {e['name'].upper()} IS STARTING NOW!",
                            color=discord.Color.red(),
                            description=f"{e['description']}\n\n**Server:** {e['server'].upper()}\n**Assemble immediately!**",
                            timestamp=discord.utils.utcnow()
                        )
                        await channel.send(content=role_ping, embed=embed)
                        conn.execute("UPDATE events SET last_triggered_date = ? WHERE id = ?", (trigger_key, e["id"]))
                        conn.commit()
            conn.close()
        except Exception as ex:
            print(f"Error in event loop: {ex}")

    @check_events.before_loop
    async def before_event_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
