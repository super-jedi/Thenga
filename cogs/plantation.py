import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional
from utils import format_money, parse_amount, discord_timestamp
import database as db

class PlantationCog(commands.Cog, name="Plantation Business"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_plantation_timer.start()

    def cog_unload(self):
        self.check_plantation_timer.cancel()

    plantation_group = app_commands.Group(name="plantation", description="Manage Family Pineapple Plantation")

    @plantation_group.command(name="plant", description="Start a new Pineapple planting cycle.")
    @app_commands.describe(
        nourish_hours="Hours until first nourishment is due (default: 2.0 hrs)",
        harvest_hours="Total hours until crop is ready for harvest (default: 4.0 hrs)",
        alert_channel="Channel where nourishment/harvest pings should be sent"
    )
    async def plant(
        self,
        interaction: discord.Interaction,
        nourish_hours: float = 2.0,
        harvest_hours: float = 4.0,
        alert_channel: Optional[discord.TextChannel] = None
    ):
        await interaction.response.defer()
        target_channel = alert_channel or interaction.channel
        now = datetime.now(timezone.utc)
        next_nourish = now + timedelta(hours=nourish_hours)
        harvest_due = now + timedelta(hours=harvest_hours)

        db.set_plantation_planted(now, next_nourish, harvest_due, target_channel.id)

        embed = discord.Embed(
            title="🍍 Pineapple Plantation Planted!",
            color=discord.Color.green(),
            description=f"Pineapple seeds planted by {interaction.user.mention}."
        )
        embed.add_field(name="🌱 Crop", value="Pineapple", inline=True)
        embed.add_field(name="💧 Next Nourish Due", value=f"{discord_timestamp(next_nourish, 'R')} ({discord_timestamp(next_nourish, 't')})", inline=True)
        embed.add_field(name="🌾 Harvest Ready", value=f"{discord_timestamp(harvest_due, 'R')} ({discord_timestamp(harvest_due, 't')})", inline=True)
        embed.add_field(name="🔔 Alerts Channel", value=target_channel.mention, inline=False)
        embed.set_footer(text="Thenga Plantation • Reminders will ping 15m before nourishment")

        await interaction.followup.send(embed=embed)

    @plantation_group.command(name="nourish", description="Log fertilization/watering and reset nourishment timer.")
    @app_commands.describe(next_hours="Hours until next nourishment is required (default: 2.0 hrs)")
    async def nourish(self, interaction: discord.Interaction, next_hours: float = 2.0):
        await interaction.response.defer()
        state = db.get_plantation_state()

        if state.get("status") != "GROWING":
            await interaction.followup.send("⚠️ No active plantation growing right now. Use `/plantation plant` to start one.")
            return

        now = datetime.now(timezone.utc)
        next_nourish = now + timedelta(hours=next_hours)
        db.update_plantation_nourish(now, next_nourish)

        embed = discord.Embed(
            title="💧 Pineapple Plantation Nourished!",
            color=discord.Color.blue(),
            description=f"Nourished & watered by {interaction.user.mention}."
        )
        embed.add_field(name="⏰ Next Nourishment", value=f"{discord_timestamp(next_nourish, 'R')} ({discord_timestamp(next_nourish, 't')})", inline=True)
        if state.get("harvest_due"):
            harvest_dt = datetime.fromisoformat(state["harvest_due"])
            embed.add_field(name="🌾 Final Harvest", value=f"{discord_timestamp(harvest_dt, 'R')}", inline=True)

        embed.set_footer(text="Thenga Plantation • Status updated")
        await interaction.followup.send(embed=embed)

    @plantation_group.command(name="harvest", description="Collect harvest, log profit, and reset plantation.")
    @app_commands.describe(
        profit="Total cash collected from harvest (e.g. 123000, 150k)",
        add_to_bank="Automatically deposit this profit into GrandRP Family Bank?"
    )
    async def harvest(self, interaction: discord.Interaction, profit: str, add_to_bank: bool = True):
        await interaction.response.defer()
        try:
            amount = parse_amount(profit)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        db.reset_plantation()

        embed = discord.Embed(
            title="🚜 Pineapple Harvest Complete!",
            color=discord.Color.gold(),
            description=f"Harvest collected by {interaction.user.mention}."
        )
        embed.add_field(name="💰 Profit Collected", value=format_money(amount), inline=True)

        if add_to_bank:
            # Auto-deposit to GrandRP bank
            tax = amount * 0.03
            net = amount - tax
            db.record_bank_transaction(
                server="grandrp",
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                tx_type="deposit",
                gross=amount,
                tax=tax,
                net=net,
                reason="Pineapple Plantation Harvest Profit"
            )
            embed.add_field(name="🏦 Auto-Banked", value=f"Added {format_money(net)} to GrandRP Bank (after 3% tax)", inline=False)

        embed.set_footer(text="Plantation is now IDLE and ready for next planting cycle.")
        await interaction.followup.send(embed=embed)

    @plantation_group.command(name="status", description="Check current status of the family pineapple plantation.")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        state = db.get_plantation_state()

        status = state.get("status", "IDLE")
        if status != "GROWING":
            await interaction.followup.send("🌱 Plantation is currently **IDLE** (No crop planted). Use `/plantation plant` when ready.")
            return

        embed = discord.Embed(
            title="🍍 Thenga Pineapple Plantation Status",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Status", value="🟢 **GROWING**", inline=True)
        embed.add_field(name="Crop", value="Pineapple", inline=True)

        if state.get("next_nourish_due"):
            nourish_dt = datetime.fromisoformat(state["next_nourish_due"])
            embed.add_field(name="💧 Next Nourish", value=f"{discord_timestamp(nourish_dt, 'R')}\n({discord_timestamp(nourish_dt, 't')})", inline=True)

        if state.get("harvest_due"):
            harvest_dt = datetime.fromisoformat(state["harvest_due"])
            embed.add_field(name="🌾 Harvest Ready", value=f"{discord_timestamp(harvest_dt, 'R')}\n({discord_timestamp(harvest_dt, 't')})", inline=True)

        if state.get("last_nourished_at"):
            last_nourish = datetime.fromisoformat(state["last_nourished_at"])
            embed.add_field(name="🕒 Last Nourished", value=f"{discord_timestamp(last_nourish, 'R')}", inline=True)

        embed.set_footer(text="Thenga Family Business Manager")
        await interaction.followup.send(embed=embed)

    # Background task to monitor timers every 60 seconds
    @tasks.loop(seconds=60)
    async def check_plantation_timer(self):
        try:
            state = db.get_plantation_state()
            if not state or state.get("status") != "GROWING":
                return

            channel_id = state.get("alert_channel_id")
            if not channel_id:
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    return

            now = datetime.now(timezone.utc)

            # Check Nourish Alert (15 minutes before due)
            if state.get("next_nourish_due") and not state.get("last_notified_nourish"):
                nourish_dt = datetime.fromisoformat(state["next_nourish_due"])
                diff = (nourish_dt - now).total_seconds()
                if 0 <= diff <= 15 * 60:
                    db.mark_plantation_notified("last_notified_nourish")
                    await channel.send(
                        f"⚠️ @here **Pineapple Plantation Alert:** Crops require nourishment in ~{int(diff/60)} minutes ({discord_timestamp(nourish_dt, 'R')})! Water and fertilize now to avoid penalties."
                    )

            # Check Harvest Alert
            if state.get("harvest_due") and not state.get("last_notified_harvest"):
                harvest_dt = datetime.fromisoformat(state["harvest_due"])
                if now >= harvest_dt:
                    db.mark_plantation_notified("last_notified_harvest")
                    await channel.send(
                        "🍍🎉 @here **Pineapple Plantation Ready for Harvest!** The crop is fully grown. Collect profit and run `/plantation harvest`!"
                    )
        except Exception as e:
            print(f"Error in plantation loop: {e}")

    @check_plantation_timer.before_loop
    async def before_timer(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(PlantationCog(bot))
