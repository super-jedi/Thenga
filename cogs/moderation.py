import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
from typing import Optional
from utils import is_admin_user

class ModerationCog(commands.Cog, name="Family Moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def find_announcement_channel(self, guild: discord.Guild, user_specified: Optional[discord.TextChannel] = None) -> Optional[discord.TextChannel]:
        if user_specified:
            return user_specified
        # Auto-detect common announcement channels in Thenga/Libra server
        for name in ["announcements-mc", "announcements-and-codes", "announcements", "logs-grp", "libra-logs"]:
            ch = discord.utils.get(guild.text_channels, name=name)
            if ch:
                return ch
        return None

    @app_commands.command(name="timeout", description="Timeout (mute) a member and broadcast announcement.")
    @app_commands.describe(
        member="The member to timeout",
        minutes="Duration of timeout in minutes",
        reason="Reason for disciplinary action",
        announcement_channel="Channel to broadcast announcement (auto-detected if blank)"
    )
    async def timeout_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: int,
        reason: str = "Disciplinary action",
        announcement_channel: Optional[discord.TextChannel] = None
    ):
        if not is_admin_user(interaction.user) and not interaction.user.guild_permissions.moderate_members and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You do not have permission to moderate members.", ephemeral=True)
            return

        await interaction.response.defer()
        duration = timedelta(minutes=minutes)

        try:
            await member.timeout(duration, reason=f"{reason} (by {interaction.user.display_name})")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to timeout user: `{e}`")
            return

        # Attempt DM
        try:
            await member.send(f"⚠️ You have been timed out in **{interaction.guild.name}** for **{minutes} minutes**.\n**Reason:** {reason}")
        except Exception:
            pass

        # Broadcast Announcement
        target_ch = self.find_announcement_channel(interaction.guild, announcement_channel)
        embed = discord.Embed(
            title="🚨 FAMILY DISCIPLINARY NOTICE: TIMEOUT",
            color=discord.Color.yellow(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="👤 Member", value=f"{member.mention} (`{member.display_name}` / `{member.id}`)", inline=False)
        embed.add_field(name="⏳ Duration", value=f"{minutes} minutes", inline=True)
        embed.add_field(name="👮 Issued By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        embed.set_footer(text="Thenga Family High Command")

        if target_ch and target_ch.permissions_for(interaction.guild.me).send_messages:
            await target_ch.send(embed=embed)
            await interaction.followup.send(f"✅ Successfully timed out {member.mention} and broadcasted to {target_ch.mention}!")
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="kick", description="Kick a member from the server and broadcast announcement.")
    @app_commands.describe(
        member="The member to kick",
        reason="Reason for kick",
        announcement_channel="Channel to broadcast announcement"
    )
    async def kick_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Inactivity or family violation",
        announcement_channel: Optional[discord.TextChannel] = None
    ):
        if not is_admin_user(interaction.user) and not interaction.user.guild_permissions.kick_members and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You do not have permission to kick members.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            await member.send(f"⚠️ You have been kicked from **{interaction.guild.name}**.\n**Reason:** {reason}")
        except Exception:
            pass

        try:
            await member.kick(reason=f"{reason} (by {interaction.user.display_name})")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to kick user: `{e}`")
            return

        target_ch = self.find_announcement_channel(interaction.guild, announcement_channel)
        embed = discord.Embed(
            title="🚨 FAMILY DISCIPLINARY NOTICE: EXPULSION / KICK",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="👤 Expelled Member", value=f"`{member.display_name}` ({member.id})", inline=False)
        embed.add_field(name="👮 Enforced By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        embed.set_footer(text="Thenga Family High Command")

        if target_ch and target_ch.permissions_for(interaction.guild.me).send_messages:
            await target_ch.send(embed=embed)
            await interaction.followup.send(f"✅ Kicked `{member.display_name}` and announced to {target_ch.mention}!")
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="ban", description="Ban a user permanently and broadcast formal announcement.")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for blacklist/ban",
        delete_message_days="Delete their messages from the last N days (0-7)",
        announcement_channel="Channel to broadcast announcement"
    )
    async def ban_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Severe family violation / theft / blacklist",
        delete_message_days: int = 0,
        announcement_channel: Optional[discord.TextChannel] = None
    ):
        if not is_admin_user(interaction.user) and not interaction.user.guild_permissions.ban_members and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You do not have permission to ban members.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            await member.send(f"🚫 You have been **permanently banned** from **{interaction.guild.name}**.\n**Reason:** {reason}")
        except Exception:
            pass

        try:
            await member.ban(reason=f"{reason} (by {interaction.user.display_name})", delete_message_days=delete_message_days)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to ban user: `{e}`")
            return

        target_ch = self.find_announcement_channel(interaction.guild, announcement_channel)
        embed = discord.Embed(
            title="⛔ FAMILY DISCIPLINARY NOTICE: PERMANENT BAN & BLACKLIST",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="👤 Banned User", value=f"`{member.display_name}` ({member.id})", inline=False)
        embed.add_field(name="👮 Issued By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        embed.set_footer(text="Thenga Family High Command • Blacklisted from Family")

        if target_ch and target_ch.permissions_for(interaction.guild.me).send_messages:
            await target_ch.send(embed=embed)
            await interaction.followup.send(f"✅ Permanently banned `{member.display_name}` and posted to {target_ch.mention}!")
        else:
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
