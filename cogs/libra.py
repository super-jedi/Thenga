import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Tuple, List, Dict
from utils import parse_amount, format_money, discord_timestamp, is_admin_user
import database as db

class LibraRPCog(commands.Cog, name="Libra RP (Fedrix)"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    libra_group = app_commands.Group(name="libra", description="Libra RP (Fedrix) Family Management")
    bank_group = app_commands.Group(name="bank", description="Libra RP Family Fund", parent=libra_group)
    vehicle_group = app_commands.Group(name="vehicle", description="Libra RP (Fedrix) Fleet", parent=libra_group)
    event_group = app_commands.Group(name="event", description="Libra RP Events Radar", parent=libra_group)

    # ==================== BANK COMMANDS (LIBRA RP - 0% TAX) ====================
    @bank_group.command(name="deposit", description="Deposit cash into Libra RP Family Account (0% tax).")
    @app_commands.describe(
        amount="Amount to deposit (e.g. 500k, 2M, 100000)",
        reason="Source of funds",
        proof="Screenshot proof of deposit"
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

        tax = 0.0 # 0% LibraRP
        net = gross
        proof_url = proof.url if proof else None

        db.record_bank_transaction("librarp", interaction.user.id, interaction.user.display_name, "deposit", gross, tax, net, reason, proof_url)
        bal = db.get_bank_balance("librarp")

        embed = discord.Embed(
            title="📥 Libra RP Family Deposit",
            color=discord.Color.blue(),
            description=f"**Deposited by:** {interaction.user.mention} (`{interaction.user.display_name}`)"
        )
        embed.add_field(name="💰 Amount Added", value=format_money(net), inline=True)
        embed.add_field(name="🏦 Libra RP Balance", value=format_money(bal["balance"]), inline=True)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        if proof_url:
            embed.set_image(url=proof_url)
        embed.set_footer(text="Fedrix • Libra RP")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="withdraw", description="Withdraw cash from Libra RP Family Account (0% tax).")
    @app_commands.describe(
        amount="Amount to withdraw (e.g. 250k, 1M, 50000)",
        reason="Reason for withdrawal",
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

        tax = 0.0
        net = gross
        proof_url = proof.url if proof else None

        db.record_bank_transaction("librarp", interaction.user.id, interaction.user.display_name, "withdraw", gross, tax, net, reason, proof_url)
        bal = db.get_bank_balance("librarp")

        embed = discord.Embed(
            title="📤 Libra RP Family Withdrawal",
            color=discord.Color.orange(),
            description=f"**Withdrawn by:** {interaction.user.mention} (`{interaction.user.display_name}`)"
        )
        embed.add_field(name="💸 Amount Withdrawn", value=format_money(net), inline=True)
        embed.add_field(name="🏦 Libra RP Balance", value=format_money(bal["balance"]), inline=True)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        if proof_url:
            embed.set_image(url=proof_url)
        embed.set_footer(text="Fedrix • Libra RP")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="balance", description="View Libra RP Family Fund Balance & Recent Transactions.")
    async def bank_balance(self, interaction: discord.Interaction):
        await interaction.response.defer()
        bal = db.get_bank_balance("librarp")
        txs = db.get_recent_transactions("librarp", limit=6)

        embed = discord.Embed(
            title="🏛️ Libra RP (Fedrix) Family Treasury",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💵 Current Family Balance", value=f"### {format_money(bal['balance'])}", inline=False)
        embed.add_field(name="📥 Total Deposited", value=format_money(bal["total_deposited"]), inline=True)
        embed.add_field(name="📤 Total Withdrawn", value=format_money(bal["total_withdrawn"]), inline=True)

        if txs:
            recent_text = ""
            for t in txs:
                icon = "📥" if t["type"] == "deposit" else "📤"
                recent_text += f"{icon} **{t['type'].upper()}**: {format_money(t['gross_amount'])} by `{t['user_name']}` — *{t['reason']}*\n"
            embed.add_field(name="📜 Recent Activity", value=recent_text, inline=False)

        embed.set_footer(text="Libra RP Rules: 0% Tax • Fedrix Family")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="set_balance", description="[Admin Only] Manually sync Libra RP balance with in-game fund.")
    @app_commands.describe(amount="New balance amount (e.g. 2189500, 2.5M)")
    async def bank_set_balance(self, interaction: discord.Interaction, amount: str):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Admin/Owner only.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            new_bal = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return
        db.set_bank_balance("librarp", new_bal)
        await interaction.followup.send(f"✅ Libra RP Family Balance updated to **{format_money(new_bal)}**.")

    # ==================== VEHICLE COMMANDS (LIBRA RP) ====================
    @vehicle_group.command(name="list", description="List all Libra RP (Fedrix) vehicles and insurance status.")
    @app_commands.describe(only_expired="Show only vehicles with expired insurance")
    async def vehicle_list(self, interaction: discord.Interaction, only_expired: bool = False):
        await interaction.response.defer()
        vehicles = db.get_vehicles("librarp")
        if not vehicles:
            await interaction.followup.send("🚗 No Libra RP vehicles registered.")
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
            title=f"🏎️ Libra RP Fedrix Fleet ({len(vehicles)} Vehicles)",
            color=discord.Color.red() if expired_list else discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        if expired_list:
            embed.add_field(name=f"⚠️ EXPIRED INSURANCE ({len(expired_list)})", value="\n".join(expired_list[:25]), inline=False)
        if insured_list and not only_expired:
            embed.add_field(name=f"🛡️ ACTIVE INSURANCE ({len(insured_list)})", value="\n".join(insured_list[:25]), inline=False)
        embed.set_footer(text="Use /libra vehicle renew [id or plate] [days] to update insurance")
        await interaction.followup.send(embed=embed)

    @vehicle_group.command(name="add", description="Add a vehicle to Libra RP garage.")
    @app_commands.describe(name="Vehicle model", plate="License plate (optional)", insurance_days="Days remaining (0 = Expired)", notes="Rank or notes")
    async def vehicle_add(self, interaction: discord.Interaction, name: str, plate: Optional[str] = None, insurance_days: int = 0, notes: str = ""):
        await interaction.response.defer()
        exp = datetime.now(timezone.utc) + timedelta(days=insurance_days) if insurance_days > 0 else None
        db.add_vehicle("librarp", name, plate, exp, notes, interaction.user.display_name)
        status = "🔴 Expired" if not exp else f"🟢 Insured ({insurance_days}d)"
        await interaction.followup.send(f"✅ Added **{name}** ({plate or 'No Plate'}) to Libra RP fleet — {status}.")

    @vehicle_group.command(name="bulk_add", description="Add multiple Libra RP vehicles.")
    async def vehicle_bulk_add(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        lines = [line.strip() for line in text.replace(",", "\n").split("\n") if line.strip()]
        for line in lines:
            parts = [p.strip() for p in line.split("|")] if "|" in line else [p.strip() for p in line.split("-")]
            name = parts[0]
            plate = parts[1] if len(parts) > 1 else None
            db.add_vehicle("librarp", name, plate, None, "Bulk added", interaction.user.display_name)
        await interaction.followup.send(f"✅ Bulk added {len(lines)} vehicles to Libra RP fleet.")

    @vehicle_group.command(name="renew", description="Renew vehicle insurance in Libra RP.")
    @app_commands.describe(identifier="License plate OR ID #", days="Days of insurance (default: 30)")
    async def vehicle_renew(self, interaction: discord.Interaction, identifier: str, days: int = 30):
        await interaction.response.defer()
        exp = datetime.now(timezone.utc) + timedelta(days=days)
        success = db.renew_vehicle_insurance(identifier, exp)
        if success:
            await interaction.followup.send(f"🛡️ Renewed insurance for Libra RP vehicle `{identifier.upper()}` for **{days} days** ({discord_timestamp(exp, 'R')})!")
        else:
            await interaction.followup.send(f"❌ Vehicle `{identifier.upper()}` not found.")

    @vehicle_group.command(name="remove", description="Remove a Libra RP vehicle.")
    @app_commands.describe(identifier="License plate OR ID # to delete")
    async def vehicle_remove(self, interaction: discord.Interaction, identifier: str):
        await interaction.response.defer()
        success = db.remove_vehicle(identifier)
        if success:
            await interaction.followup.send(f"🗑️ Removed vehicle `{identifier.upper()}` from Libra RP fleet.")
        else:
            await interaction.followup.send(f"❌ Vehicle `{identifier.upper()}` not found.")

    # ==================== EVENT COMMANDS (LIBRA RP EXCLUSIVE) ====================
    @event_group.command(name="list", description="List all scheduled Libra RP daily events.")
    async def event_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events = db.get_events("librarp")
        if not events:
            await interaction.followup.send("📅 No events scheduled. Use `/libra event add` to create one.")
            return

        embed = discord.Embed(title="🎮 Libra RP (Fedrix) Daily Event Radar", color=discord.Color.purple(), timestamp=discord.utils.utcnow())
        for e in events:
            role_txt = f"<@&{e['role_id']}>" if e.get("role_id") else "No role ping"
            ch_txt = f"<#{e['channel_id']}>" if e.get("channel_id") else "Default Channel"
            val = f"⏰ **{e['time_utc']} UTC** | 📢 {ch_txt} | 🔔 {role_txt}\n*{e['description']}*"
            embed.add_field(name=f"ID #{e['id']} — {e['name']}", value=val, inline=False)
        embed.set_footer(text="Pings 10m before and at start time.")
        await interaction.followup.send(embed=embed)

    @event_group.command(name="add", description="Add an automated daily event alert in Libra RP.")
    @app_commands.describe(name="Event name (e.g. Crown Holder)", time_utc="24-hr UTC time (HH:MM)", channel="Channel for alerts", role_to_ping="Role to mention", description="Notes")
    async def event_add(self, interaction: discord.Interaction, name: str, time_utc: str, channel: discord.TextChannel, role_to_ping: Optional[discord.Role] = None, description: str = "Family gathering"):
        await interaction.response.defer()
        try:
            parts = time_utc.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            formatted = f"{h:02d}:{m:02d}"
        except Exception:
            await interaction.followup.send("❌ Use 24-hr UTC format `HH:MM`, e.g. `10:00` or `13:00`.")
            return

        r_id = role_to_ping.id if role_to_ping else None
        db.add_event("librarp", name, formatted, description, r_id, channel.id)
        await interaction.followup.send(f"✅ Added Libra RP Event alert: **{name}** at `{formatted} UTC` in {channel.mention}.")

    @event_group.command(name="remove", description="Delete an event schedule.")
    @app_commands.describe(event_id="Event ID to remove")
    async def event_remove(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer()
        if db.remove_event(event_id):
            await interaction.followup.send(f"🗑️ Removed event `#{event_id}`.")
        else:
            await interaction.followup.send(f"❌ Event `#{event_id}` not found.")

    @event_group.command(name="test", description="Send test alert for an event.")
    @app_commands.describe(event_id="Event ID to test")
    async def event_test(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        events = db.get_events("librarp")
        event = next((e for e in events if e["id"] == event_id), None)
        if not event:
            await interaction.followup.send(f"❌ Event `#{event_id}` not found.")
            return
        ch = self.bot.get_channel(event["channel_id"]) or interaction.channel
        role_ping = f"<@&{event['role_id']}> " if event.get("role_id") else ""
        embed = discord.Embed(
            title=f"🚨 [TEST ALERT] {event['name'].upper()} IN 10 MINUTES!",
            color=discord.Color.red(),
            description=f"{event['description']}\n\n**Server:** LIBRA RP\n**Assemble immediately!**"
        )
        await ch.send(content=role_ping, embed=embed)
        await interaction.followup.send("✅ Test alert sent!")

    # ==================== CLAN WARNINGS & DISCIPLINARY SYSTEM ====================
    def find_libra_target(self, identifier: str) -> Optional[dict]:
        conn = db.get_connection()
        clean = identifier.strip().replace("#", "")
        if clean.isdigit():
            m = conn.execute("SELECT * FROM libra_members WHERE id = ?", (int(clean),)).fetchone()
            if m:
                conn.close()
                return dict(m)
        query = f"%{identifier.strip().lower()}%"
        m = conn.execute("SELECT * FROM libra_members WHERE LOWER(name) LIKE ? ORDER BY rank_level ASC LIMIT 1", (query,)).fetchone()
        conn.close()
        return dict(m) if m else None

    def can_actor_manage(self, user: Any, target_level: int) -> tuple[bool, str]:
        if is_admin_user(user):
            return True, ""
        
        conn = db.get_connection()
        uid = str(getattr(user, "id", ""))
        row = conn.execute("SELECT rank_level, name FROM libra_members WHERE discord_id = ?", (uid,)).fetchone()
        conn.close()
        if not row:
            return False, "❌ You do not have a linked Libra RP character with leadership authority."
        
        actor_level = row["rank_level"]
        if actor_level not in [1, 2, 3]:
            return False, f"❌ Disciplinary authority is restricted to Rank 1 (Leader), Rank 2 (Co-Leader), and Rank 3 (Supervisor). Your rank is Lv {actor_level} ({row['name']})."
        
        if actor_level >= target_level:
            return False, f"❌ You cannot discipline an operative of equal or higher rank (Lv {target_level})."
        
        return True, ""

    @libra_group.command(name="warn", description="Issue a Libra RP clan warning strike to a member.")
    @app_commands.describe(
        member="In-game character name or ID # (e.g. 5392 or Cameo)",
        reason="Reason for the clan warning"
    )
    async def libra_warn(self, interaction: discord.Interaction, member: str, reason: str):
        await interaction.response.defer()
        target = self.find_libra_target(member)
        if not target:
            await interaction.followup.send(f"❌ Member `{member}` not found in Libra RP Fedrix roster.")
            return
        
        allowed, err_msg = self.can_actor_manage(interaction.user, target["rank_level"])
        if not allowed:
            await interaction.followup.send(err_msg)
            return
        
        res = db.add_libra_warning(target["id"], reason, issued_by=interaction.user.display_name)
        if not res.get("success"):
            await interaction.followup.send(f"❌ Failed to issue warning: {res.get('error')}")
            return
        
        strike = res["strike_number"]
        color = discord.Color.gold() if strike == 1 else (discord.Color.orange() if strike == 2 else discord.Color.red())
        
        embed = discord.Embed(
            title="⚠️ LIBRA RP (FEDRIX) DISCIPLINARY STRIKE",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Operative", value=f"**{target['name']}** (`ID #{target['id']}`)", inline=True)
        embed.add_field(name="Clan Rank", value=f"Lv {target['rank_level']} {target['rank_name']}", inline=True)
        embed.add_field(name="Strike Count", value=f"**{strike} / 3 Strikes**", inline=True)
        embed.add_field(name="Disciplinary Reason", value=reason, inline=False)
        embed.add_field(name="Issued By", value=interaction.user.mention, inline=False)
        
        if strike >= 3:
            embed.add_field(
                name="🚨 ACTION REQUIRED",
                value="Operative has accumulated **3 strikes**. Immediate suspension or clan expulsion is recommended.",
                inline=False
            )
        embed.set_footer(text="Fedrix Clan Disciplinary System • Isolated from Grand RP & Discord")
        
        # DM member if linked
        if target.get("discord_id"):
            try:
                user_obj = await self.bot.fetch_user(int(target["discord_id"]))
                if user_obj:
                    await user_obj.send(f"⚠️ **LIBRA RP CLAN DISCIPLINARY NOTICE**\nYou have received Strike #{strike}/3 in Fedrix Clan.\n**Reason:** {reason}\n**Issued By:** {interaction.user.display_name}")
            except Exception:
                pass
        
        await interaction.followup.send(embed=embed)

    @libra_group.command(name="warnings", description="View active Libra RP clan warnings for an operative.")
    @app_commands.describe(member="In-game character name or ID #")
    async def libra_warnings(self, interaction: discord.Interaction, member: str):
        await interaction.response.defer()
        target = self.find_libra_target(member)
        if not target:
            await interaction.followup.send(f"❌ Member `{member}` not found in Libra RP Fedrix roster.")
            return
        
        warns = db.get_libra_warnings(target["id"])
        w_cnt = target.get("warnings") or 0
        
        embed = discord.Embed(
            title=f"📜 Libra RP Disciplinary Record: {target['name']}",
            color=discord.Color.red() if w_cnt >= 3 else (discord.Color.gold() if w_cnt > 0 else discord.Color.green()),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Operative", value=f"**{target['name']}** (`ID #{target['id']}`)", inline=True)
        embed.add_field(name="Rank", value=f"Lv {target['rank_level']} {target['rank_name']}", inline=True)
        embed.add_field(name="Strike Standing", value=f"**{w_cnt} / 3 Active Strikes**", inline=True)
        
        if not warns:
            embed.description = "✅ **Clean Record:** This operative has 0 active warnings or strikes."
        else:
            lines = []
            for w in warns:
                lines.append(f"• **Strike #{w['strike_number']}** ({w['created_at'][:10]}): {w['reason']} *(issued by {w['issued_by']})*")
            embed.description = "\n".join(lines)
        
        embed.set_footer(text="Fedrix Clan Disciplinary Record")
        await interaction.followup.send(embed=embed)

    @libra_group.command(name="clearwarn", description="Clear all Libra RP warnings for an operative.")
    @app_commands.describe(member="In-game character name or ID #")
    async def libra_clearwarn(self, interaction: discord.Interaction, member: str):
        await interaction.response.defer()
        target = self.find_libra_target(member)
        if not target:
            await interaction.followup.send(f"❌ Member `{member}` not found.")
            return
        
        # Only Rank 1 (Leader), Rank 2 (Co-Leader), or Bot Admin
        conn = db.get_connection()
        row = conn.execute("SELECT rank_level FROM libra_members WHERE discord_id = ?", (str(interaction.user.id),)).fetchone()
        conn.close()
        actor_lvl = row["rank_level"] if row else 99
        
        if not is_admin_user(interaction.user) and actor_lvl not in [1, 2]:
            await interaction.followup.send("❌ Only Clan Leader (Lv 1), Co-Leader (Lv 2), or Bot Admins can clear disciplinary strikes.")
            return
        
        db.clear_libra_warnings(target["id"])
        
        embed = discord.Embed(
            title="✓ LIBRA RP DISCIPLINARY RECORD CLEARED",
            color=discord.Color.green(),
            description=f"All active warnings for **{target['name']}** (`ID #{target['id']}`) have been cleared.\nStanding restored to **0/3 Clean Record** by {interaction.user.mention}.",
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Fedrix Clan Disciplinary System")
        await interaction.followup.send(embed=embed)

    # Prefix command fallbacks
    @commands.command(name="librawarn", aliases=["warnlibra", "lwarn"])
    async def prefix_librawarn(self, ctx: commands.Context, member: str, *, reason: str = "Disciplinary violation"):
        target = self.find_libra_target(member)
        if not target:
            await ctx.send(f"❌ Member `{member}` not found in Libra RP Fedrix roster.")
            return
        allowed, err_msg = self.can_actor_manage(ctx.author, target["rank_level"])
        if not allowed:
            await ctx.send(err_msg)
            return
        res = db.add_libra_warning(target["id"], reason, issued_by=ctx.author.display_name)
        await ctx.send(f"⚠️ **Warning Issued:** {target['name']} (`ID #{target['id']}`) now has **{res['strike_number']}/3 Strikes**. Reason: *{reason}*")

    @commands.command(name="librawarnings", aliases=["lwarns"])
    async def prefix_librawarnings(self, ctx: commands.Context, member: str):
        target = self.find_libra_target(member)
        if not target:
            await ctx.send(f"❌ Member `{member}` not found.")
            return
        warns = db.get_libra_warnings(target["id"])
        w_cnt = target.get("warnings") or 0
        if not warns:
            await ctx.send(f"✅ **{target['name']}** has a clean record (0 active strikes).")
        else:
            msg = f"📜 **{target['name']}** (`ID #{target['id']}`) - **{w_cnt}/3 Active Strikes:**\n"
            for w in warns:
                msg += f"• Strike #{w['strike_number']}: {w['reason']} *(by {w['issued_by']})*\n"
            await ctx.send(msg)

    @commands.command(name="clearwarn", aliases=["lclearwarn"])
    async def prefix_clearwarn(self, ctx: commands.Context, member: str):
        target = self.find_libra_target(member)
        if not target:
            await ctx.send(f"❌ Member `{member}` not found.")
            return
        conn = db.get_connection()
        row = conn.execute("SELECT rank_level FROM libra_members WHERE discord_id = ?", (str(ctx.author.id),)).fetchone()
        conn.close()
        actor_lvl = row["rank_level"] if row else 99
        if not is_admin_user(ctx.author) and actor_lvl not in [1, 2]:
            await ctx.send("❌ Only Clan Leader (Lv 1), Co-Leader (Lv 2), or Bot Admins can clear strikes.")
            return
        db.clear_libra_warnings(target["id"])
        await ctx.send(f"✅ Disciplinary record cleared for **{target['name']}** (`ID #{target['id']}`). Restored to clean standing.")

    @tasks.loop(seconds=60)
    async def check_events(self):
        try:
            now_utc = datetime.now(timezone.utc)
            cur_time_str = now_utc.strftime("%H:%M")
            cur_date_str = now_utc.strftime("%Y-%m-%d")
            events = db.get_events("librarp")
            conn = db.get_connection()
            for e in events:
                e_time = e["time_utc"]
                trigger_key = f"{e['id']}_{cur_date_str}_{cur_time_str}"
                if cur_time_str == e_time and e.get("last_triggered_date") != trigger_key:
                    channel = self.bot.get_channel(e["channel_id"])
                    if channel:
                        role_ping = f"<@&{e['role_id']}> " if e.get("role_id") else ""
                        embed = discord.Embed(
                            title=f"⚔️ {e['name'].upper()} IS STARTING NOW!",
                            color=discord.Color.red(),
                            description=f"{e['description']}\n\n**Server:** LIBRA RP\n**Assemble immediately!**",
                            timestamp=discord.utils.utcnow()
                        )
                        await channel.send(content=role_ping, embed=embed)
                        conn.execute("UPDATE events SET last_triggered_date = ? WHERE id = ?", (trigger_key, e["id"]))
                        conn.commit()
            conn.close()
        except Exception:
            pass

    @check_events.before_loop
    async def before_event_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(LibraRPCog(bot))
