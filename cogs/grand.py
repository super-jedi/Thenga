import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional
from utils import parse_amount, format_money, discord_timestamp
import database as db

class GrandRPCog(commands.Cog, name="Grand RP (EN2)"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_plantation_timer.start()

    def cog_unload(self):
        self.check_plantation_timer.cancel()

    grand_group = app_commands.Group(name="grand", description="Grand RP (EN2) Family Management")
    bank_group = app_commands.Group(name="bank", description="Grand RP Family Fund", parent=grand_group)
    vehicle_group = app_commands.Group(name="vehicle", description="Grand RP Vehicle Fleet", parent=grand_group)

    # ==================== BANK COMMANDS (GRAND RP) ====================
    @bank_group.command(name="deposit", description="Deposit cash into Grand RP Family Account (3% tax).")
    @app_commands.describe(
        amount="Amount to deposit (e.g. 500k, 4.85M, 100000)",
        reason="Source of funds (e.g. Plantation, Office Tasks, Weapon sales)",
        proof="Screenshot proof of in-game deposit"
    )
    async def bank_deposit(self, interaction: discord.Interaction, amount: str, reason: str, proof: Optional[discord.Attachment] = None):
        await interaction.response.defer()
        try:
            gross = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        if gross <= 0:
            await interaction.followup.send("❌ Deposit amount must be greater than 0.")
            return

        tax = gross * 0.03 # 3% GrandRP in-game tax
        net = gross - tax
        proof_url = proof.url if proof else None

        db.record_bank_transaction("grandrp", interaction.user.id, interaction.user.display_name, "deposit", gross, tax, net, reason, proof_url)
        bal = db.get_bank_balance("grandrp")

        embed = discord.Embed(
            title="📥 Grand RP Family Deposit",
            color=discord.Color.green(),
            description=f"**Deposited by:** {interaction.user.mention} (`{interaction.user.display_name}`)"
        )
        embed.add_field(name="💰 Gross Amount", value=format_money(gross), inline=True)
        embed.add_field(name="🏛️ In-Game Tax (3%)", value=f"-{format_money(tax)}", inline=True)
        embed.add_field(name="✅ Net Added to Fam", value=format_money(net), inline=True)
        embed.add_field(name="🏦 Grand RP Balance", value=format_money(bal["balance"]), inline=False)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        if proof_url:
            embed.set_image(url=proof_url)
        embed.set_footer(text="Thenga Family • Grand RP EN2")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="withdraw", description="Withdraw cash from Grand RP Family Account (5% tax).")
    @app_commands.describe(
        amount="Amount to withdraw (e.g. 650k, 3M, 100000)",
        reason="Reason for withdrawal (e.g. Family fines, Weapons, Personal)",
        proof="Screenshot proof of withdrawal"
    )
    async def bank_withdraw(self, interaction: discord.Interaction, amount: str, reason: str, proof: Optional[discord.Attachment] = None):
        await interaction.response.defer()
        try:
            gross = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        if gross <= 0:
            await interaction.followup.send("❌ Withdrawal amount must be greater than 0.")
            return

        tax = gross * 0.05 # 5% GrandRP in-game tax
        net = gross - tax
        proof_url = proof.url if proof else None

        db.record_bank_transaction("grandrp", interaction.user.id, interaction.user.display_name, "withdraw", gross, tax, net, reason, proof_url)
        bal = db.get_bank_balance("grandrp")

        embed = discord.Embed(
            title="📤 Grand RP Family Withdrawal",
            color=discord.Color.red(),
            description=f"**Withdrawn by:** {interaction.user.mention} (`{interaction.user.display_name}`)"
        )
        embed.add_field(name="💸 Gross Withdrawn", value=format_money(gross), inline=True)
        embed.add_field(name="🏛️ In-Game Tax (5%)", value=f"-{format_money(tax)}", inline=True)
        embed.add_field(name="💵 Net Cash Received", value=format_money(net), inline=True)
        embed.add_field(name="🏦 Grand RP Remaining Balance", value=format_money(bal["balance"]), inline=False)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        if proof_url:
            embed.set_image(url=proof_url)
        embed.set_footer(text="Thenga Family • Grand RP EN2")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="balance", description="View Grand RP Family Fund Balance & Recent Transactions.")
    async def bank_balance(self, interaction: discord.Interaction):
        await interaction.response.defer()
        bal = db.get_bank_balance("grandrp")
        txs = db.get_recent_transactions("grandrp", limit=6)

        embed = discord.Embed(
            title="🏛️ Grand RP (EN2) Family Treasury",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💵 Current Family Balance", value=f"### {format_money(bal['balance'])}", inline=False)
        embed.add_field(name="📥 Total Deposited", value=format_money(bal["total_deposited"]), inline=True)
        embed.add_field(name="📤 Total Withdrawn", value=format_money(bal["total_withdrawn"]), inline=True)
        embed.add_field(name="🧾 Taxes Absorbed", value=format_money(bal["total_tax_paid"]), inline=True)

        if txs:
            recent_text = ""
            for t in txs:
                icon = "📥" if t["type"] == "deposit" else "📤"
                recent_text += f"{icon} **{t['type'].upper()}**: {format_money(t['gross_amount'])} by `{t['user_name']}` — *{t['reason']}*\n"
            embed.add_field(name="📜 Recent Activity", value=recent_text, inline=False)

        embed.set_footer(text="Grand RP Rules: 3% Deposit Tax / 5% Withdrawal Tax")
        await interaction.followup.send(embed=embed)

    # ==================== VEHICLE COMMANDS (GRAND RP) ====================
    @vehicle_group.command(name="list", description="List all Grand RP vehicles and insurance status.")
    @app_commands.describe(only_expired="Show only vehicles with expired insurance")
    async def vehicle_list(self, interaction: discord.Interaction, only_expired: bool = False):
        await interaction.response.defer()
        vehicles = db.get_vehicles("grandrp")
        if not vehicles:
            await interaction.followup.send("🚗 No Grand RP vehicles registered.")
            return

        now = datetime.now(timezone.utc)
        expired_list = []
        insured_list = []

        for v in vehicles:
            v_id = v["id"]
            name = v["name"]
            plate = v.get("plate")
            plate_str = f"(`{plate}`)" if plate else "*(No Plate)*"
            notes_str = f" • *{v['notes']}*" if v.get("notes") else ""

            if not v.get("insurance_expiry"):
                expired_list.append(f"🔴 `#{v_id}` **{name}** {plate_str}{notes_str} — **EXPIRED**")
            else:
                exp_dt = datetime.fromisoformat(v["insurance_expiry"])
                if now > exp_dt:
                    expired_list.append(f"🔴 `#{v_id}` **{name}** {plate_str}{notes_str} — Expired {discord_timestamp(exp_dt, 'R')}")
                else:
                    insured_list.append(f"🟢 `#{v_id}` **{name}** {plate_str}{notes_str} — Valid until {discord_timestamp(exp_dt, 'R')}")

        embed = discord.Embed(
            title=f"🏎️ Grand RP Fleet Inventory ({len(vehicles)} Vehicles)",
            color=discord.Color.red() if expired_list else discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        if expired_list:
            embed.add_field(name=f"⚠️ EXPIRED INSURANCE ({len(expired_list)})", value="\n".join(expired_list[:25]), inline=False)
        if insured_list and not only_expired:
            embed.add_field(name=f"🛡️ ACTIVE INSURANCE ({len(insured_list)})", value="\n".join(insured_list[:25]), inline=False)
        embed.set_footer(text="Use /grand vehicle renew [id or plate] [days] to update insurance")
        await interaction.followup.send(embed=embed)

    @vehicle_group.command(name="renew", description="Renew vehicle insurance in Grand RP.")
    @app_commands.describe(identifier="License plate OR ID #", days="Days of insurance (default: 30)")
    async def vehicle_renew(self, interaction: discord.Interaction, identifier: str, days: int = 30):
        await interaction.response.defer()
        exp = datetime.now(timezone.utc) + timedelta(days=days)
        success = db.renew_vehicle_insurance(identifier, exp)
        if success:
            await interaction.followup.send(f"🛡️ Renewed insurance for Grand RP vehicle `{identifier.upper()}` for **{days} days** ({discord_timestamp(exp, 'R')})!")
        else:
            await interaction.followup.send(f"❌ Vehicle `{identifier.upper()}` not found.")

    @vehicle_group.command(name="remove", description="Remove a Grand RP vehicle.")
    @app_commands.describe(identifier="License plate OR ID # to delete")
    async def vehicle_remove(self, interaction: discord.Interaction, identifier: str):
        await interaction.response.defer()
        success = db.remove_vehicle(identifier)
        if success:
            await interaction.followup.send(f"🗑️ Removed vehicle `{identifier.upper()}` from Grand RP fleet.")
        else:
            await interaction.followup.send(f"❌ Vehicle `{identifier.upper()}` not found.")

    # ==================== PLANTATION BACKGROUND TIMER ====================
    @tasks.loop(seconds=60)
    async def check_plantation_timer(self):
        try:
            state = db.get_plantation_state()
            if not state or state.get("status") != "GROWING":
                return
            channel_id = state.get("alert_channel_id")
            if not channel_id:
                return
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            if not channel:
                return

            now = datetime.now(timezone.utc)
            if state.get("next_nourish_due") and not state.get("last_notified_nourish"):
                nourish_dt = datetime.fromisoformat(state["next_nourish_due"])
                diff = (nourish_dt - now).total_seconds()
                if 0 <= diff <= 15 * 60:
                    db.mark_plantation_notified("last_notified_nourish")
                    await channel.send(f"⚠️ @here **Grand RP Pineapple Alert:** Crops need nourishment in ~{int(diff/60)}m ({discord_timestamp(nourish_dt, 'R')})!")

            if state.get("harvest_due") and not state.get("last_notified_harvest"):
                harvest_dt = datetime.fromisoformat(state["harvest_due"])
                if now >= harvest_dt:
                    db.mark_plantation_notified("last_notified_harvest")
                    await channel.send("🍍🎉 @here **Pineapple Plantation Ready for Harvest!** Open the Dashboard to collect profit!")
        except Exception:
            pass

    @check_plantation_timer.before_loop
    async def before_timer(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(GrandRPCog(bot))
