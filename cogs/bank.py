import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from utils import parse_amount, format_money, detect_server
import database as db

class BankCog(commands.Cog, name="Family Bank"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    bank_group = app_commands.Group(name="bank", description="Manage GrandRP and LibraRP Family Finances")

    @bank_group.command(name="deposit", description="Deposit cash into the Family Account.")
    @app_commands.describe(
        amount="Amount to deposit (e.g. 500k, 4.85M, 100000)",
        reason="Source of funds (e.g. Plantation profit, Office task, Weapon sales)",
        proof="Screenshot of in-game deposit confirmation",
        server="Which server's bank account (auto-detected if blank)"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP (3% Deposit Tax)", value="grandrp"),
        app_commands.Choice(name="Libra RP (0% Deposit Tax)", value="librarp")
    ])
    async def deposit(
        self,
        interaction: discord.Interaction,
        amount: str,
        reason: str,
        proof: Optional[discord.Attachment] = None,
        server: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        try:
            gross = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        if gross <= 0:
            await interaction.followup.send("❌ Deposit amount must be greater than 0.")
            return

        # Tax calculation
        if target_server == "grandrp":
            tax_rate = 0.03 # 3% GrandRP in-game family tax
            tax = gross * tax_rate
            net = gross - tax
        else:
            tax_rate = 0.0 # 0% LibraRP
            tax = 0.0
            net = gross

        proof_url = proof.url if proof else None

        db.record_bank_transaction(
            server=target_server,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            tx_type="deposit",
            gross=gross,
            tax=tax,
            net=net,
            reason=reason,
            proof_url=proof_url
        )

        bal_info = db.get_bank_balance(target_server)

        # Build Receipt Embed
        embed = discord.Embed(
            title=f"📥 Family Account Deposit — {target_server.upper()}",
            color=discord.Color.green(),
            description=f"**Deposited by:** {interaction.user.mention} (`{interaction.user.display_name}`)"
        )
        embed.add_field(name="💰 Gross Amount", value=format_money(gross), inline=True)
        if tax > 0:
            embed.add_field(name="🏛️ In-Game Tax (3%)", value=f"-{format_money(tax)}", inline=True)
            embed.add_field(name="✅ Net Added to Fam", value=format_money(net), inline=True)
        else:
            embed.add_field(name="🏛️ In-Game Tax", value="0% (None)", inline=True)
            embed.add_field(name="✅ Net Added to Fam", value=format_money(net), inline=True)

        embed.add_field(name="🏦 New Family Balance", value=format_money(bal_info["balance"]), inline=False)
        embed.add_field(name="📝 Reason", value=reason, inline=False)

        if proof_url:
            embed.set_image(url=proof_url)

        embed.set_footer(text=f"Thenga Family Bank • {target_server.upper()}")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="withdraw", description="Withdraw cash from the Family Account.")
    @app_commands.describe(
        amount="Amount to withdraw (e.g. 650k, 3M, 100000)",
        reason="Reason for withdrawal (e.g. Family fines, Gun buy, Loan, Personal)",
        proof="Screenshot of in-game withdrawal confirmation",
        server="Which server's bank account (auto-detected if blank)"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP (5% Withdraw Tax)", value="grandrp"),
        app_commands.Choice(name="Libra RP (0% Withdraw Tax)", value="librarp")
    ])
    async def withdraw(
        self,
        interaction: discord.Interaction,
        amount: str,
        reason: str,
        proof: Optional[discord.Attachment] = None,
        server: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        try:
            gross = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        if gross <= 0:
            await interaction.followup.send("❌ Withdrawal amount must be greater than 0.")
            return

        bal_info = db.get_bank_balance(target_server)
        current_bal = bal_info["balance"]

        # Tax calculation
        if target_server == "grandrp":
            tax_rate = 0.05 # 5% GrandRP in-game tax
            tax = gross * tax_rate
            net = gross - tax
        else:
            tax_rate = 0.0
            tax = 0.0
            net = gross

        proof_url = proof.url if proof else None

        db.record_bank_transaction(
            server=target_server,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            tx_type="withdraw",
            gross=gross,
            tax=tax,
            net=net,
            reason=reason,
            proof_url=proof_url
        )

        bal_info = db.get_bank_balance(target_server)

        embed = discord.Embed(
            title=f"📤 Family Account Withdrawal — {target_server.upper()}",
            color=discord.Color.red(),
            description=f"**Withdrawn by:** {interaction.user.mention} (`{interaction.user.display_name}`)"
        )
        embed.add_field(name="💸 Gross Withdrawn", value=format_money(gross), inline=True)
        if tax > 0:
            embed.add_field(name="🏛️ In-Game Tax (5%)", value=f"-{format_money(tax)}", inline=True)
            embed.add_field(name="💵 Net Cash Received", value=format_money(net), inline=True)
        else:
            embed.add_field(name="🏛️ In-Game Tax", value="0% (None)", inline=True)
            embed.add_field(name="💵 Net Cash Received", value=format_money(net), inline=True)

        embed.add_field(name="🏦 Remaining Family Balance", value=format_money(bal_info["balance"]), inline=False)
        embed.add_field(name="📝 Reason", value=reason, inline=False)

        if proof_url:
            embed.set_image(url=proof_url)

        embed.set_footer(text=f"Thenga Family Bank • {target_server.upper()}")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="balance", description="View Family Bank Balance, Taxes Paid, and Active Loans.")
    @app_commands.describe(server="Which server's balance to check")
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP", value="grandrp"),
        app_commands.Choice(name="Libra RP", value="librarp")
    ])
    async def balance(self, interaction: discord.Interaction, server: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        bal_info = db.get_bank_balance(target_server)
        txs = db.get_recent_transactions(target_server, limit=5)
        loans = db.get_active_loans(target_server)

        embed = discord.Embed(
            title=f"🏛️ Thenga Family Treasury — {target_server.upper()}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💵 Current Family Balance", value=f"### {format_money(bal_info['balance'])}", inline=False)
        embed.add_field(name="📥 Total Deposited", value=format_money(bal_info["total_deposited"]), inline=True)
        embed.add_field(name="📤 Total Withdrawn", value=format_money(bal_info["total_withdrawn"]), inline=True)
        embed.add_field(name="🧾 Total Tax Absorbed", value=format_money(bal_info["total_tax_paid"]), inline=True)

        # Active loans section
        if loans:
            loan_text = ""
            for l in loans:
                remaining = l["amount"] - l["repaid_amount"]
                loan_text += f"• **ID #{l['id']}** | <@{l['user_id']}>: Owes **{format_money(remaining)}** (Terms: {l['terms']})\n"
            embed.add_field(name="⚠️ Active Unpaid Member Loans", value=loan_text, inline=False)
        else:
            embed.add_field(name="🤝 Active Member Loans", value="None. All family debts are cleared!", inline=False)

        # Recent transactions
        if txs:
            recent_text = ""
            for t in txs:
                icon = "📥" if t["type"] == "deposit" else "📤"
                recent_text += f"{icon} **{t['type'].upper()}**: {format_money(t['gross_amount'])} by `{t['user_name']}` — *{t['reason']}*\n"
            embed.add_field(name="📜 Recent Activity", value=recent_text, inline=False)

        tax_info = "3% Deposit / 5% Withdrawal" if target_server == "grandrp" else "0% (No in-game tax)"
        embed.set_footer(text=f"Tax Rules: {tax_info} • Thenga Family")
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="loan", description="Issue or log a family loan to a member.")
    @app_commands.describe(
        user="Member taking the loan",
        amount="Loan amount (e.g. 5M, 2.5M, 500k)",
        terms="Payback terms (e.g. Repay by Sunday, 10% interest, for business car)",
        server="Server context (GrandRP or LibraRP)"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP", value="grandrp"),
        app_commands.Choice(name="Libra RP", value="librarp")
    ])
    async def issue_loan(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: str,
        terms: str,
        server: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer()
        target_server = detect_server(interaction, server.value if server else None)

        try:
            loan_amt = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        db.create_loan(target_server, user.id, user.display_name, loan_amt, terms)

        embed = discord.Embed(
            title=f"📋 New Family Loan Issued — {target_server.upper()}",
            color=discord.Color.orange(),
            description=f"A family loan has been registered for {user.mention}."
        )
        embed.add_field(name="👤 Borrower", value=f"{user.mention} (`{user.display_name}`)", inline=True)
        embed.add_field(name="💰 Amount", value=format_money(loan_amt), inline=True)
        embed.add_field(name="📌 Terms & Deadline", value=terms, inline=False)
        embed.set_footer(text="Thenga Bank • Use /bank repay when returning funds")

        await interaction.followup.send(embed=embed)

    @bank_group.command(name="repay", description="Log a loan repayment.")
    @app_commands.describe(
        loan_id="ID of the loan (find with /bank balance)",
        amount="Amount being repaid (e.g. 2M, 500k)"
    )
    async def repay(self, interaction: discord.Interaction, loan_id: int, amount: str):
        await interaction.response.defer()

        try:
            repay_amt = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        updated_loan = db.repay_loan(loan_id, repay_amt)
        if not updated_loan:
            await interaction.followup.send(f"❌ Loan ID `#{loan_id}` was not found.")
            return

        remaining = updated_loan["amount"] - updated_loan["repaid_amount"]
        status_text = "🎉 FULLY REPAID!" if updated_loan["status"] == "REPAID" else f"Still owes {format_money(remaining)}"

        embed = discord.Embed(
            title=f"✅ Loan Repayment Logged — #{loan_id}",
            color=discord.Color.green(),
            description=f"Borrower: <@{updated_loan['user_id']}>\nAmount Repaid: **{format_money(repay_amt)}**\nStatus: **{status_text}**"
        )
        await interaction.followup.send(embed=embed)

    @bank_group.command(name="set_balance", description="[Admin Only] Manually adjust family balance to sync with in-game.")
    @app_commands.describe(
        server="Which server's balance to set",
        amount="New balance amount (e.g. 15.5M, 0, 500000)"
    )
    @app_commands.choices(server=[
        app_commands.Choice(name="Grand RP", value="grandrp"),
        app_commands.Choice(name="Libra RP", value="librarp")
    ])
    async def set_balance(self, interaction: discord.Interaction, server: app_commands.Choice[str], amount: str):
        # Allow server owner or administrators
        if not interaction.user.guild_permissions.administrator and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Only server administrators/owners can adjust the balance manually.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            new_bal = parse_amount(amount)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
            return

        db.set_bank_balance(server.value, new_bal)
        await interaction.followup.send(f"✅ **{server.name}** family balance has been updated to **{format_money(new_bal)}**.")

async def setup(bot: commands.Bot):
    await bot.add_cog(BankCog(bot))
