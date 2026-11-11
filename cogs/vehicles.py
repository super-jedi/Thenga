import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Optional
from utils import detect_server, discord_timestamp
import database as db

class VehiclesCog(commands.Cog, name="Vehicle Fleet"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    vehicle_group = app_commands.Group(name="vehicle", description="Manage Family Vehicle Fleet & Insurance")

    @vehicle_group.command(name="add", description="Add a vehicle to the family garage (defaults to EXPIRED insurance).")
    @app_commands.describe(
        name="Vehicle model (e.g. Bugatti Chiron, Jugular, Toros)",
        plate="License plate number",
        server="Which RP server this vehicle belongs to",
        insurance_days="Days of insurance remaining (0 = Expired)",
        notes="Notes (e.g. Parked at Family House, Level 4 Engine, Assigned to Superjedi)"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP", value="grandrp"),
        app_commands.Choice(name="Libra RP", value="librarp")
    ])
    async def add_vehicle(
        self,
        interaction: discord.Interaction,
        name: str,
        plate: str,
        server: Optional[app_commands.Choice[str]] = None,
        insurance_days: int = 0,
        notes: str = ""
    ):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        expiry_dt = None
        if insurance_days > 0:
            expiry_dt = datetime.now(timezone.utc) + timedelta(days=insurance_days)

        db.add_vehicle(
            server=target_server,
            name=name.strip(),
            plate=plate.strip().upper(),
            expiry_dt=expiry_dt,
            notes=notes.strip(),
            added_by=interaction.user.display_name
        )

        status_text = "🔴 **EXPIRED**" if not expiry_dt else f"🟢 Insured until {discord_timestamp(expiry_dt, 'F')}"

        embed = discord.Embed(
            title="🚗 Family Vehicle Added",
            color=discord.Color.red() if not expiry_dt else discord.Color.green(),
            description=f"**{name}** has been registered into the {target_server.upper()} fleet."
        )
        embed.add_field(name="🔢 License Plate", value=f"`{plate.upper()}`", inline=True)
        embed.add_field(name="🛡️ Insurance", value=status_text, inline=True)
        if notes:
            embed.add_field(name="📝 Notes", value=notes, inline=False)
        embed.set_footer(text=f"Added by {interaction.user.display_name} • Thenga Fleet")

        await interaction.followup.send(embed=embed)

    @vehicle_group.command(name="bulk_add", description="Add multiple vehicles at once (all set to Expired insurance).")
    @app_commands.describe(
        text="List vehicles separated by commas or lines (e.g. 'Chiron | ABC-1, Jugular | XYZ-2')",
        server="Which server these vehicles belong to"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP", value="grandrp"),
        app_commands.Choice(name="Libra RP", value="librarp")
    ])
    async def bulk_add(self, interaction: discord.Interaction, text: str, server: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        lines = [line.strip() for line in text.replace(",", "\n").split("\n") if line.strip()]
        added = []

        for line in lines:
            parts = [p.strip() for p in line.split("|")] if "|" in line else [p.strip() for p in line.split("-")]
            if len(parts) >= 2:
                v_name, v_plate = parts[0], parts[1]
            else:
                v_name = parts[0]
                v_plate = f"GEN-{abs(hash(v_name)) % 10000:04d}"

            db.add_vehicle(
                server=target_server,
                name=v_name,
                plate=v_plate.upper(),
                expiry_dt=None, # Expired by default
                notes="Bulk added",
                added_by=interaction.user.display_name
            )
            added.append(f"• **{v_name}** (`{v_plate.upper()}`) — 🔴 Expired")

        embed = discord.Embed(
            title=f"🚗 Bulk Registered {len(added)} Vehicles ({target_server.upper()})",
            color=discord.Color.blue(),
            description="\n".join(added[:25])
        )
        embed.set_footer(text="All registered with Expired insurance. Use /vehicle renew when insured.")
        await interaction.followup.send(embed=embed)

    @vehicle_group.command(name="list", description="List all family vehicles and their insurance status.")
    @app_commands.describe(
        server="Filter by server",
        only_expired="Show only vehicles with expired insurance"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="All Servers", value="all"),
        app_commands.Choice(name="Grand RP", value="grandrp"),
        app_commands.Choice(name="Libra RP", value="librarp")
    ])
    async def list_vehicles(
        self,
        interaction: discord.Interaction,
        server: Optional[app_commands.Choice[str]] = None,
        only_expired: bool = False
    ):
        await interaction.response.defer()
        chosen = server.value if server and server.value != "all" else None
        vehicles = db.get_vehicles(chosen)

        if not vehicles:
            await interaction.followup.send("🚗 No vehicles currently registered. Use `/vehicle add` to add some!")
            return

        now = datetime.now(timezone.utc)
        expired_list = []
        insured_list = []

        for v in vehicles:
            name = v["name"]
            plate = v["plate"]
            srv = v["server"].upper()
            notes_str = f" *({v['notes']})*" if v.get("notes") else ""

            if not v.get("insurance_expiry"):
                expired_list.append(f"🔴 `[{srv}]` **{name}** (`{plate}`){notes_str} — **EXPIRED**")
            else:
                exp_dt = datetime.fromisoformat(v["insurance_expiry"])
                if now > exp_dt:
                    expired_list.append(f"🔴 `[{srv}]` **{name}** (`{plate}`){notes_str} — Expired {discord_timestamp(exp_dt, 'R')}")
                else:
                    insured_list.append(f"🟢 `[{srv}]` **{name}** (`{plate}`){notes_str} — Valid until {discord_timestamp(exp_dt, 'R')}")

        embed = discord.Embed(
            title="🏎️ Thenga Family Fleet Inventory",
            color=discord.Color.red() if expired_list else discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        if expired_list:
            embed.add_field(
                name=f"⚠️ EXPIRED INSURANCE ({len(expired_list)})",
                value="\n".join(expired_list[:20]) + ("\n*...and more*" if len(expired_list) > 20 else ""),
                inline=False
            )

        if insured_list and not only_expired:
            embed.add_field(
                name=f"🛡️ ACTIVE INSURANCE ({len(insured_list)})",
                value="\n".join(insured_list[:20]) + ("\n*...and more*" if len(insured_list) > 20 else ""),
                inline=False
            )

        embed.set_footer(text=f"Total: {len(vehicles)} vehicles • Use /vehicle renew [plate] to update insurance")
        await interaction.followup.send(embed=embed)

    @vehicle_group.command(name="renew", description="Renew or update insurance for a vehicle.")
    @app_commands.describe(
        plate="License plate of the car",
        days="How many days of insurance were purchased (default: 30)"
    )
    async def renew_insurance(self, interaction: discord.Interaction, plate: str, days: int = 30):
        await interaction.response.defer()
        new_expiry = datetime.now(timezone.utc) + timedelta(days=days)
        success = db.renew_vehicle_insurance(plate, new_expiry)

        if not success:
            await interaction.followup.send(f"❌ Vehicle with plate `{plate.upper()}` was not found in the fleet.")
            return

        embed = discord.Embed(
            title="🛡️ Vehicle Insurance Renewed!",
            color=discord.Color.green(),
            description=f"Insurance for plate **`{plate.upper()}`** has been renewed for **{days} days**."
        )
        embed.add_field(name="Valid Until", value=f"{discord_timestamp(new_expiry, 'F')}\n({discord_timestamp(new_expiry, 'R')})")
        embed.set_footer(text="Thenga Fleet Manager")
        await interaction.followup.send(embed=embed)

    @vehicle_group.command(name="remove", description="Remove a vehicle from the fleet.")
    @app_commands.describe(plate="License plate to delete")
    async def remove_vehicle(self, interaction: discord.Interaction, plate: str):
        await interaction.response.defer()
        success = db.remove_vehicle(plate)
        if success:
            await interaction.followup.send(f"🗑️ Removed vehicle with plate **`{plate.upper()}`** from the fleet.")
        else:
            await interaction.followup.send(f"❌ Plate `{plate.upper()}` not found.")

async def setup(bot: commands.Bot):
    await bot.add_cog(VehiclesCog(bot))
