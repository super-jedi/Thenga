import os
import json
import base64
import hmac
import hashlib
import aiohttp
from aiohttp import web
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

import database as db
from utils import format_money, parse_amount, is_admin_user

load_dotenv()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1567865230829035530")
ENABLE_DEV_LOGIN = os.getenv("ENABLE_DEV_LOGIN", "false").lower() == "true"
SECRET_KEY = os.getenv("SESSION_SECRET") or os.urandom(32).hex()

def get_client_secret() -> str:
    return os.getenv("DISCORD_CLIENT_SECRET", "").strip()

def create_session_token(user_data: dict) -> str:
    raw = json.dumps(user_data).encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()
    return f"{base64.urlsafe_b64encode(raw).decode()}.{sig}"

def parse_session_token(token: str) -> Optional[dict]:
    try:
        raw_b64, sig = token.split(".")
        raw = base64.urlsafe_b64decode(raw_b64.encode())
        expected_sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    return None

def get_current_user(request: web.Request) -> Optional[dict]:
    cookie = request.cookies.get("thenga_user")
    if cookie:
        return parse_session_token(cookie)
    return None

# ==========================================
# AUTH HANDLERS
# ==========================================
async def handle_login(request: web.Request):
    redirect_uri = f"{request.scheme}://{request.host}/auth/callback"
    client_secret = get_client_secret()
    if client_secret:
        discord_url = (
            f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
            f"&redirect_uri={redirect_uri}&response_type=code&scope=identify"
        )
        return web.HTTPFound(discord_url)
    elif ENABLE_DEV_LOGIN:
        # Quick login enabled only for local testing when ENABLE_DEV_LOGIN=true
        return web.HTTPFound(f"/auth/quick_login?user=superjedi")
    else:
        return web.Response(
            text="Discord OAuth is not configured. Please add DISCORD_CLIENT_SECRET in .env to enable login.",
            status=503,
            content_type="text/plain"
        )

async def handle_quick_login(request: web.Request):
    if not ENABLE_DEV_LOGIN:
        return web.Response(text="Quick login is disabled in production.", status=403, content_type="text/plain")

    username = request.query.get("user", "superjedi")
    user_info = {
        "id": "1567865230829035530",
        "username": username,
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"
    }
    token = create_session_token(user_info)
    response = web.HTTPFound("/")
    response.set_cookie("thenga_user", token, max_age=86400 * 14, httponly=True)
    return response

async def handle_callback(request: web.Request):
    code = request.query.get("code")
    if not code:
        return web.HTTPFound("/")

    client_secret = get_client_secret()
    redirect_uri = f"{request.scheme}://{request.host}/auth/callback"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with aiohttp.ClientSession() as session:
        async with session.post("https://discord.com/api/oauth2/token", data=data, headers=headers) as resp:
            token_json = await resp.json()
            access_token = token_json.get("access_token")

        if not access_token:
            return web.HTTPFound("/")

        auth_headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get("https://discord.com/api/users/@me", headers=auth_headers) as user_resp:
            user_data = await user_resp.json()

    avatar = user_data.get("avatar")
    uid = user_data.get("id")
    avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png" if avatar else "https://cdn.discordapp.com/embed/avatars/0.png"

    user_info = {
        "id": uid,
        "username": user_data.get("username", "Member"),
        "avatar_url": avatar_url
    }
    token = create_session_token(user_info)
    response = web.HTTPFound("/")
    response.set_cookie("thenga_user", token, max_age=86400 * 14, httponly=True)
    return response

async def handle_logout(request: web.Request):
    response = web.HTTPFound("/")
    response.del_cookie("thenga_user")
    return response

# ==========================================
# HTML TEMPLATES & PAGES
# ==========================================
COMMON_CSS = """
:root {
    --bg-dark: #080c14;
    --card-bg: #111724;
    --card-border: #1d283c;
    --accent: #f59e0b; /* Warm Coconut Amber */
    --accent-light: #fbbf24;
    --accent-hover: #d97706;
    --accent-glow: rgba(245, 158, 11, 0.35);
    --gold: #fbbf24;
    --green: #10b981; /* Lush Kerala Emerald */
    --green-glow: rgba(16, 185, 129, 0.25);
    --red: #ef4444;
    --purple: #a855f7;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}
header {
    background: #0d121d;
    border-bottom: 1px solid var(--card-border);
    padding: 16px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}
.brand {
    font-size: 19px;
    font-weight: 800;
    color: var(--gold);
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
    letter-spacing: -0.5px;
}
.brand-badge {
    font-size: 11px;
    font-weight: 700;
    color: #fbbf24;
    background: rgba(245, 158, 11, 0.15);
    border: 1px solid rgba(245, 158, 11, 0.4);
    padding: 2px 8px;
    border-radius: 9999px;
    letter-spacing: 0.5px;
}
.user-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    padding: 6px 14px;
    border-radius: 9999px;
}
.user-avatar { width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid var(--accent); }
.logout-btn { color: var(--red); text-decoration: none; font-size: 13px; font-weight: 600; margin-left: 8px; }
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 14px;
    border-radius: 8px;
    cursor: pointer;
    border: none;
    text-decoration: none;
    transition: all 0.2s;
}
.btn-primary { 
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); 
    color: #080c14; 
}
.btn-primary:hover { 
    background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); 
    box-shadow: 0 0 18px var(--accent-glow); 
}
.btn-green { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; }
.btn-green:hover { box-shadow: 0 0 15px var(--green-glow); }
.btn-red { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; }
.btn-purple { background: linear-gradient(135deg, #a855f7 0%, #9333ea 100%); color: white; }
.btn-secondary { background: #1f293d; color: white; border: 1px solid #334155; }
.btn-secondary:hover { background: #334155; }
.tabs {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--card-border);
    padding-bottom: 12px;
}
.tab-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 15px;
    font-weight: 700;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
}
.tab-btn.active { 
    background: rgba(245, 158, 11, 0.15); 
    color: var(--gold); 
    border: 1px solid rgba(245, 158, 11, 0.3);
}
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 24px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
}
.stat-val { font-size: 26px; font-weight: 800; color: #fff; margin-top: 4px; }
.stat-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
input, select {
    width: 100%;
    background: #090d16;
    border: 1px solid #243048;
    color: #fff;
    padding: 12px;
    border-radius: 8px;
    font-size: 14px;
    margin-top: 6px;
    margin-bottom: 16px;
    transition: border-color 0.2s, box-shadow 0.2s;
}
input:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 10px var(--accent-glow); }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--card-border); font-size: 14px; }
th { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 700; }
.badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
.badge-green { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
.badge-purple { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; }
"""

def render_header(user: dict, subtitle: str = "") -> str:
    is_adm = is_admin_user(user)
    badge_html = (
        '<span class="badge" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; font-size: 11px; margin-left: 6px;">👑 FOUNDER / ADMIN</span>'
        if is_adm else
        '<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; font-size: 11px; margin-left: 6px;">MEMBER</span>'
    )
    sub_tag = (
        f'<span style="font-size:14px; color:#94a3b8; font-weight:500;">/ {subtitle}</span>'
        if subtitle else
        '<span class="brand-badge">MALAYALI CLUB</span>'
    )
    return f"""
    <header>
        <a href="/" class="brand">
            <div style="width:36px; height:36px; border-radius:50%; background:radial-gradient(circle, rgba(245,158,11,0.25), rgba(18,24,36,0.9)); border:1.5px solid rgba(245,158,11,0.5); display:flex; align-items:center; justify-content:center; font-size:20px; box-shadow: 0 0 12px rgba(245,158,11,0.2);">🥥</div>
            <span>THENGA NETWORK</span> {sub_tag}
        </a>
        <div class="user-pill">
            <img class="user-avatar" src="{user['avatar_url']}">
            <span style="font-weight:700; color:#fff;">{user['username']}</span>
            {badge_html}
            <a href="/auth/logout" class="logout-btn">Logout</a>
        </div>
    </header>
    """

# ==========================================
# PAGE 1: LANDING & GAME SELECTOR
# ==========================================
async def handle_home(request: web.Request):
    user = get_current_user(request)

    if not user:
        html = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Thenga Network Management Dashboard</title>
                <style>{COMMON_CSS}</style>
            </head>
            <body style="justify-content: center; align-items: center; text-align: center; padding: 20px;">
                <div class="card" style="max-width: 520px; width: 100%; padding: 48px 36px; border: 1px solid rgba(245, 158, 11, 0.45); box-shadow: 0 12px 50px rgba(0, 0, 0, 0.7), 0 0 40px rgba(245, 158, 11, 0.15); border-radius: 20px;">
                    <div style="width: 90px; height: 90px; margin: 0 auto 18px; border-radius: 50%; background: radial-gradient(circle, rgba(245, 158, 11, 0.22) 0%, rgba(18, 24, 38, 0.95) 70%); display: flex; align-items: center; justify-content: center; border: 2px solid rgba(245, 158, 11, 0.55); box-shadow: 0 0 30px rgba(245, 158, 11, 0.35);">
                        <span style="font-size: 50px; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.6));">🥥</span>
                    </div>
                    <h1 style="color: #fbbf24; font-size: 25px; font-weight: 800; margin-bottom: 8px; letter-spacing: -0.5px;">Thenga Network Management Dashboard</h1>
                    <p style="color: #94a3b8; margin-bottom: 30px; font-size: 15px; line-height: 1.5;">
                        Integrated command center for <b style="color: #f8fafc;">Thenga Network Malayali Club</b>
                    </p>
                    <a href="/auth/login" class="btn" style="width: 100%; padding: 15px; font-size: 16px; font-weight: 700; background: #5865F2; color: #fff; border-radius: 10px; box-shadow: 0 4px 18px rgba(88, 101, 242, 0.4); text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 10px;">
                        <svg style="width: 22px; height: 22px; fill: currentColor;" viewBox="0 0 24 24"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0a12.64 12.64 0 0 0-.617-1.25a.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10.2 10.2 0 0 0 .372-.292a.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127a12.299 12.299 0 0 1-1.873.894a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028a19.839 19.839 0 0 0 6.002-3.03a.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418z"/></svg>
                        Login with Discord
                    </a>
                    <div style="margin-top: 22px; font-size: 12px; color: #64748b; display: flex; align-items: center; justify-content: center; gap: 6px;">
                        <span>🔒</span> Official Discord OAuth2 • Verified Members Only
                    </div>
                </div>
            </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    grand_bal = db.get_bank_balance("grandrp")
    libra_bal = db.get_bank_balance("librarp")
    grand_v = db.get_vehicles("grandrp")
    libra_v = db.get_vehicles("librarp")

    html = f"""
    <!DOCTYPE html>
    <html>
        <head><title>Operations Hub • Thenga Network</title><style>{COMMON_CSS}</style></head>
        <body>
            {render_header(user)}

            <main style="max-width: 960px; margin: 40px auto; width: 100%; padding: 0 20px;">
                <div style="text-align: center; margin-bottom: 36px;">
                    <h1 style="font-size: 32px; font-weight: 800; color: #fff;">Select Family Operations</h1>
                    <p style="color: var(--text-secondary); margin-top: 6px;">Choose your active GTA RP server dashboard</p>
                </div>

                <div class="grid-2">
                    <!-- Grand RP Card -->
                    <a href="/grand" style="text-decoration: none; color: inherit;">
                        <div class="card" style="cursor: pointer; transition: transform 0.2s, border-color 0.2s; border-color: #3b82f6;" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='none'">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                                <span style="font-size: 32px;">🌆</span>
                                <span class="badge badge-green">3% / 5% Tax</span>
                            </div>
                            <h2 style="font-size: 24px; color: #60a5fa; margin-bottom: 8px;">Grand RP (EN2)</h2>
                            <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
                                Manage Family Fund, 31 Vehicles, and Pineapple Plantation Business.
                            </p>
                            <div style="border-top: 1px solid var(--card-border); padding-top: 16px; display: flex; justify-content: space-between;">
                                <div>
                                    <div class="stat-label">Treasury</div>
                                    <div style="font-weight: 700; color: #fff; font-size: 16px;">{format_money(grand_bal['balance'])}</div>
                                </div>
                                <div>
                                    <div class="stat-label">Fleet</div>
                                    <div style="font-weight: 700; color: #fff; font-size: 16px;">{len(grand_v)} Cars</div>
                                </div>
                                <div>
                                    <div class="stat-label">Plantation</div>
                                    <div style="font-weight: 700; color: #34d399; font-size: 16px;">Pineapple</div>
                                </div>
                            </div>
                        </div>
                    </a>

                    <!-- Libra RP Card -->
                    <a href="/libra" style="text-decoration: none; color: inherit;">
                        <div class="card" style="cursor: pointer; transition: transform 0.2s, border-color 0.2s; border-color: #a855f7;" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='none'">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                                <span style="font-size: 32px;">⚖️</span>
                                <span class="badge badge-purple">0% Tax • Active</span>
                            </div>
                            <h2 style="font-size: 24px; color: #c084fc; margin-bottom: 8px;">Libra RP (Fedrix)</h2>
                            <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
                                Manage Fedrix Clan Bank, 24 Vehicles, and Daily Events Radar.
                            </p>
                            <div style="border-top: 1px solid var(--card-border); padding-top: 16px; display: flex; justify-content: space-between;">
                                <div>
                                    <div class="stat-label">Treasury</div>
                                    <div style="font-weight: 700; color: #fff; font-size: 16px;">{format_money(libra_bal['balance'])}</div>
                                </div>
                                <div>
                                    <div class="stat-label">Fleet</div>
                                    <div style="font-weight: 700; color: #fff; font-size: 16px;">{len(libra_v)} Cars</div>
                                </div>
                                <div>
                                    <div class="stat-label">Events</div>
                                    <div style="font-weight: 700; color: #c084fc; font-size: 16px;">3 Scheduled</div>
                                </div>
                            </div>
                        </div>
                    </a>
                </div>
            </main>
        </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

# ==========================================
# PAGE 2: GRAND RP DASHBOARD (/grand)
# ==========================================
async def handle_grand(request: web.Request):
    user = get_current_user(request)
    if not user:
        return web.HTTPFound("/")

    bal = db.get_bank_balance("grandrp")
    txs = db.get_recent_transactions("grandrp", limit=20)
    vehicles = db.get_vehicles("grandrp")
    plantation = db.get_plantation_state()

    # Build vehicles table rows
    now = datetime.now(timezone.utc)
    veh_rows = ""
    for v in vehicles:
        plate = v.get("plate") or "*(No Plate)*"
        exp = v.get("insurance_expiry")
        is_exp = True
        exp_txt = "EXPIRED"
        if exp:
            exp_dt = datetime.fromisoformat(exp)
            if now < exp_dt:
                is_exp = False
                exp_txt = exp_dt.strftime("%Y-%m-%d")

        badge = '<span class="badge badge-red">EXPIRED</span>' if is_exp else f'<span class="badge badge-green">{exp_txt}</span>'
        veh_rows += f"""
        <tr>
            <td><b>#{v['id']}</b></td>
            <td><b>{v['name']}</b></td>
            <td><code>{plate}</code></td>
            <td>{v.get('notes') or '-'}</td>
            <td>{badge}</td>
            <td>
                <button class="btn btn-primary" style="padding: 4px 10px; font-size: 12px;" onclick="renewVehicle('{v['id']}')">🛡️ +30d</button>
                <button class="btn btn-red" style="padding: 4px 10px; font-size: 12px;" onclick="removeVehicle('{v['id']}')">🗑️</button>
            </td>
        </tr>
        """

    # Build transaction rows
    tx_rows = ""
    for t in txs:
        icon = '<span class="badge badge-green">DEPOSIT</span>' if t['type'] == 'deposit' else '<span class="badge badge-red">WITHDRAW</span>'
        tx_rows += f"""
        <tr>
            <td>{icon}</td>
            <td><b>{format_money(t['gross_amount'])}</b></td>
            <td>-{format_money(t['tax_amount'])}</td>
            <td><b>{format_money(t['net_amount'])}</b></td>
            <td>{t['user_name']}</td>
            <td>{t['reason']}</td>
            <td style="color:#64748b; font-size:12px;">{t['created_at']}</td>
        </tr>
        """

    plant_status = plantation.get("status", "IDLE")

    html = f"""
    <!DOCTYPE html>
    <html>
        <head><title>Grand RP (EN2) • Thenga Network</title><style>{COMMON_CSS}</style></head>
        <body>
            {render_header(user, "Grand RP (EN2)")}

            <main style="max-width: 1200px; margin: 24px auto; width: 100%; padding: 0 20px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                    <div>
                        <a href="/" style="color:var(--text-secondary); text-decoration:none; font-size:13px; font-weight:600;">← Back to Game Selection</a>
                        <h1 style="color:#60a5fa; margin-top:4px;">🌆 Grand RP Family Operations</h1>
                    </div>
                </div>

                <div class="tabs">
                    <button class="tab-btn active" onclick="showTab('bank')">🏦 Family Treasury</button>
                    <button class="tab-btn" onclick="showTab('garage')">🏎️ Garage Fleet ({len(vehicles)})</button>
                    <button class="tab-btn" onclick="showTab('plantation')">🍍 Pineapple Plantation</button>
                </div>

                <!-- TAB 1: BANK -->
                <div id="tab-bank">
                    <div class="grid-3" style="margin-bottom: 24px;">
                        <div class="card">
                            <div class="stat-label">Current Family Fund</div>
                            <div class="stat-val" style="color:#38bdf8;">{format_money(bal['balance'])}</div>
                        </div>
                        <div class="card">
                            <div class="stat-label">Total Deposited</div>
                            <div class="stat-val" style="color:#10b981;">{format_money(bal['total_deposited'])}</div>
                        </div>
                        <div class="card">
                            <div class="stat-label">Total Withdrawn</div>
                            <div class="stat-val" style="color:#ef4444;">{format_money(bal['total_withdrawn'])}</div>
                        </div>
                        <div class="card">
                            <div class="stat-label">In-Game Taxes Absorbed</div>
                            <div class="stat-val" style="color:#f59e0b;">{format_money(bal['total_tax_paid'])}</div>
                        </div>
                    </div>

                    <div class="grid-2" style="margin-bottom: 30px;">
                        <!-- Deposit Form -->
                        <div class="card">
                            <h3 style="color:#10b981; margin-bottom:12px;">📥 Deposit to Family Fund (3% Tax)</h3>
                            <label>Amount (e.g. 500k, 4.85M, 1000000):</label>
                            <input id="dep-amt" type="text" placeholder="1M" oninput="calcDeposit()">
                            <label>Source / Reason:</label>
                            <input id="dep-reason" type="text" placeholder="Plantation, Office tasks, Sales">
                            <div id="dep-preview" style="font-size:13px; color:#94a3b8; margin-bottom:12px;">3% Tax: $0 | Net Added: $0</div>
                            <button class="btn btn-green" style="width:100%;" onclick="submitDeposit('grandrp')">Confirm Deposit</button>
                        </div>

                        <!-- Withdraw Form -->
                        <div class="card">
                            <h3 style="color:#ef4444; margin-bottom:12px;">📤 Withdraw from Family Fund (5% Tax)</h3>
                            <label>Amount (e.g. 650k, 2M):</label>
                            <input id="with-amt" type="text" placeholder="500k" oninput="calcWithdraw()">
                            <label>Reason / Purpose:</label>
                            <input id="with-reason" type="text" placeholder="Family fines, Personal, Weapons">
                            <div id="with-preview" style="font-size:13px; color:#94a3b8; margin-bottom:12px;">5% Tax: $0 | Net Cash Received: $0</div>
                            <button class="btn btn-red" style="width:100%;" onclick="submitWithdraw('grandrp')">Confirm Withdrawal</button>
                        </div>
                    </div>

                    <div class="card">
                        <h3>📜 Recent Grand RP Transactions</h3>
                        <table>
                            <thead>
                                <tr><th>Type</th><th>Gross</th><th>Tax</th><th>Net</th><th>Member</th><th>Reason</th><th>Date</th></tr>
                            </thead>
                            <tbody>{tx_rows}</tbody>
                        </table>
                    </div>
                </div>

                <!-- TAB 2: GARAGE -->
                <div id="tab-garage" style="display:none;">
                    <div class="card" style="margin-bottom: 20px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h3>🚗 Add Vehicle to Grand RP</h3>
                            <div style="display:flex; gap:10px;">
                                <input id="veh-name" type="text" placeholder="Vehicle Name (e.g. Chiron)" style="margin:0; width:180px;">
                                <input id="veh-plate" type="text" placeholder="Plate (optional)" style="margin:0; width:140px;">
                                <input id="veh-days" type="number" placeholder="Days (0=Exp)" style="margin:0; width:110px;">
                                <button class="btn btn-primary" onclick="addVehicle('grandrp')">+ Add Car</button>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>Grand RP Fleet ({len(vehicles)} Vehicles)</h3>
                        <table>
                            <thead>
                                <tr><th>ID</th><th>Vehicle Name</th><th>Plate</th><th>Notes</th><th>Insurance Status</th><th>Actions</th></tr>
                            </thead>
                            <tbody>{veh_rows}</tbody>
                        </table>
                    </div>
                </div>

                <!-- TAB 3: PLANTATION -->
                <div id="tab-plantation" style="display:none;">
                    <div class="card" style="margin-bottom: 24px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                            <h2>🍍 Pineapple Plantation Business</h2>
                            <span class="badge { 'badge-green' if plant_status == 'GROWING' else 'badge-red' }">{plant_status}</span>
                        </div>
                        <p style="color:var(--text-secondary); margin-bottom:20px;">
                            Pineapple crop cycle management with live watering countdown and profit calculation.
                        </p>
                        <div style="display:flex; gap:16px;">
                            <button class="btn btn-green" onclick="plantCrop()">🌱 Plant Pineapple (2h nourish, 4h harvest)</button>
                            <button class="btn btn-primary" onclick="nourishCrop()">💧 Nourish Now (+2h)</button>
                            <button class="btn btn-purple" onclick="harvestCrop()">🚜 Collect Harvest & Bank</button>
                        </div>
                    </div>
                </div>
            </main>

            <script>
                function showTab(tab) {{
                    document.getElementById('tab-bank').style.display = tab === 'bank' ? 'block' : 'none';
                    document.getElementById('tab-garage').style.display = tab === 'garage' ? 'block' : 'none';
                    document.getElementById('tab-plantation').style.display = tab === 'plantation' ? 'block' : 'none';
                    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                    event.target.classList.add('active');
                }}

                function parseVal(s) {{
                    s = s.trim().toUpperCase().replace('$', '').replace(/,/g, '');
                    if (s.endsWith('M')) return parseFloat(s) * 1000000;
                    if (s.endsWith('K')) return parseFloat(s) * 1000;
                    return parseFloat(s) || 0;
                }}

                function calcDeposit() {{
                    let v = parseVal(document.getElementById('dep-amt').value);
                    let tax = v * 0.03;
                    let net = v - tax;
                    document.getElementById('dep-preview').innerText = `3% Tax: $${{tax.toLocaleString()}} | Net Added: $${{net.toLocaleString()}}`;
                }}

                function calcWithdraw() {{
                    let v = parseVal(document.getElementById('with-amt').value);
                    let tax = v * 0.05;
                    let net = v - tax;
                    document.getElementById('with-preview').innerText = `5% Tax: $${{tax.toLocaleString()}} | Net Cash: $${{net.toLocaleString()}}`;
                }}

                async function submitDeposit(server) {{
                    let amt = document.getElementById('dep-amt').value;
                    let reason = document.getElementById('dep-reason').value || "Web Deposit";
                    let res = await fetch('/api/bank/deposit', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ server, amount: amt, reason }})
                    }});
                    let d = await res.json();
                    if (d.success) {{ alert("Deposit successful!"); location.reload(); }}
                    else alert("Error: " + d.error);
                }}

                async function submitWithdraw(server) {{
                    let amt = document.getElementById('with-amt').value;
                    let reason = document.getElementById('with-reason').value || "Web Withdrawal";
                    let res = await fetch('/api/bank/withdraw', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ server, amount: amt, reason }})
                    }});
                    let d = await res.json();
                    if (d.success) {{ alert("Withdrawal logged!"); location.reload(); }}
                    else alert("Error: " + d.error);
                }}

                async function renewVehicle(id) {{
                    let res = await fetch('/api/vehicle/renew', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ identifier: id, days: 30 }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                    else alert(d.error);
                }}

                async function removeVehicle(id) {{
                    if (!confirm("Are you sure you want to remove vehicle #" + id + "?")) return;
                    let res = await fetch('/api/vehicle/remove', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ identifier: id }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                }}

                async function addVehicle(server) {{
                    let name = document.getElementById('veh-name').value;
                    let plate = document.getElementById('veh-plate').value;
                    let days = parseInt(document.getElementById('veh-days').value) || 0;
                    if (!name) return alert("Vehicle name required");
                    let res = await fetch('/api/vehicle/add', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ server, name, plate, insurance_days: days }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                    else alert(d.error);
                }}

                async function plantCrop() {{
                    let res = await fetch('/api/plantation/plant', {{ method: 'POST' }});
                    let d = await res.json();
                    if (d.success) {{ alert("Pineapple planted!"); location.reload(); }}
                }}
                async function nourishCrop() {{
                    let res = await fetch('/api/plantation/nourish', {{ method: 'POST' }});
                    let d = await res.json();
                    if (d.success) {{ alert("Pineapple nourished!"); location.reload(); }}
                    else alert(d.error);
                }}
                async function harvestCrop() {{
                    let profit = prompt("Enter total harvest profit amount:", "123000");
                    if (!profit) return;
                    let res = await fetch('/api/plantation/harvest', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ profit, add_to_bank: true }})
                    }});
                    let d = await res.json();
                    if (d.success) {{ alert("Harvest collected & banked!"); location.reload(); }}
                    else alert(d.error);
                }}
            </script>
        </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

# ==========================================
# PAGE 3: LIBRA RP DASHBOARD (/libra)
# ==========================================
async def handle_libra(request: web.Request):
    user = get_current_user(request)
    if not user:
        return web.HTTPFound("/")

    bal = db.get_bank_balance("librarp")
    txs = db.get_recent_transactions("librarp", limit=20)
    vehicles = db.get_vehicles("librarp")
    events = db.get_events("librarp")

    now = datetime.now(timezone.utc)
    veh_rows = ""
    for v in vehicles:
        plate = v.get("plate") or "*(No Plate)*"
        exp = v.get("insurance_expiry")
        is_exp = True
        exp_txt = "EXPIRED"
        if exp:
            exp_dt = datetime.fromisoformat(exp)
            if now < exp_dt:
                is_exp = False
                exp_txt = exp_dt.strftime("%Y-%m-%d")

        badge = '<span class="badge badge-red">EXPIRED</span>' if is_exp else f'<span class="badge badge-green">{exp_txt}</span>'
        veh_rows += f"""
        <tr>
            <td><b>#{v['id']}</b></td>
            <td><b>{v['name']}</b></td>
            <td><code>{plate}</code></td>
            <td><span class="badge badge-purple">{v.get('notes') or 'Rank 1'}</span></td>
            <td>{badge}</td>
            <td>
                <button class="btn btn-primary" style="padding: 4px 10px; font-size: 12px;" onclick="renewVehicle('{v['id']}')">🛡️ +30d</button>
                <button class="btn btn-red" style="padding: 4px 10px; font-size: 12px;" onclick="removeVehicle('{v['id']}')">🗑️</button>
            </td>
        </tr>
        """

    tx_rows = ""
    for t in txs:
        icon = '<span class="badge badge-green">DEPOSIT</span>' if t['type'] == 'deposit' else '<span class="badge badge-red">WITHDRAW</span>'
        tx_rows += f"""
        <tr>
            <td>{icon}</td>
            <td><b>{format_money(t['gross_amount'])}</b></td>
            <td>{t['user_name']}</td>
            <td>{t['reason']}</td>
            <td style="color:#64748b; font-size:12px;">{t['created_at']}</td>
        </tr>
        """

    event_cards = ""
    for e in events:
        event_cards += f"""
        <div class="card" style="border-left: 4px solid var(--purple);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 style="color:#c084fc;">{e['name']}</h3>
                <span class="badge badge-purple">{e['time_utc']} UTC</span>
            </div>
            <p style="color:var(--text-secondary); margin-top:8px; font-size:14px;">{e['description']}</p>
            <div style="margin-top:12px; display:flex; justify-content:flex-end; gap:8px;">
                <button class="btn btn-secondary" style="padding:4px 8px; font-size:12px;" onclick="removeEvent({e['id']})">Remove</button>
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
        <head><title>Libra RP (Fedrix) • Thenga Network</title><style>{COMMON_CSS}</style></head>
        <body>
            {render_header(user, "Libra RP (Fedrix)")}

            <main style="max-width: 1200px; margin: 24px auto; width: 100%; padding: 0 20px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                    <div>
                        <a href="/" style="color:var(--text-secondary); text-decoration:none; font-size:13px; font-weight:600;">← Back to Game Selection</a>
                        <h1 style="color:#c084fc; margin-top:4px;">⚖️ Libra RP (Fedrix) Operations</h1>
                    </div>
                </div>

                <div class="tabs">
                    <button class="tab-btn active" onclick="showTab('bank')">🏦 Fedrix Fund</button>
                    <button class="tab-btn" onclick="showTab('garage')">🏎️ Fedrix Fleet ({len(vehicles)})</button>
                    <button class="tab-btn" onclick="showTab('events')">⚔️ Events Radar ({len(events)})</button>
                </div>

                <!-- TAB 1: BANK -->
                <div id="tab-bank">
                    <div class="grid-3" style="margin-bottom: 24px;">
                        <div class="card">
                            <div class="stat-label">Libra RP Treasury</div>
                            <div class="stat-val" style="color:#c084fc;">{format_money(bal['balance'])}</div>
                        </div>
                        <div class="card">
                            <div class="stat-label">Total Deposited</div>
                            <div class="stat-val" style="color:#10b981;">{format_money(bal['total_deposited'])}</div>
                        </div>
                        <div class="card">
                            <div class="stat-label">Total Withdrawn</div>
                            <div class="stat-val" style="color:#ef4444;">{format_money(bal['total_withdrawn'])}</div>
                        </div>
                    </div>

                    <div class="grid-2" style="margin-bottom: 30px;">
                        <div class="card">
                            <h3 style="color:#10b981; margin-bottom:12px;">📥 Deposit to Libra Fund (0% Tax)</h3>
                            <label>Amount:</label>
                            <input id="dep-amt" type="text" placeholder="250k or 1M">
                            <label>Reason:</label>
                            <input id="dep-reason" type="text" placeholder="Event bonus, Car sale, Clan task">
                            <button class="btn btn-green" style="width:100%;" onclick="submitDeposit('librarp')">Confirm Deposit</button>
                        </div>

                        <div class="card">
                            <h3 style="color:#ef4444; margin-bottom:12px;">📤 Withdraw from Libra Fund (0% Tax)</h3>
                            <label>Amount:</label>
                            <input id="with-amt" type="text" placeholder="500k">
                            <label>Reason:</label>
                            <input id="with-reason" type="text" placeholder="Weapons, Clan car purchase">
                            <button class="btn btn-red" style="width:100%;" onclick="submitWithdraw('librarp')">Confirm Withdrawal</button>
                        </div>
                    </div>

                    <div class="card">
                        <h3>📜 Recent Libra RP Transactions</h3>
                        <table>
                            <thead><tr><th>Type</th><th>Amount</th><th>Member</th><th>Reason</th><th>Date</th></tr></thead>
                            <tbody>{tx_rows}</tbody>
                        </table>
                    </div>
                </div>

                <!-- TAB 2: GARAGE -->
                <div id="tab-garage" style="display:none;">
                    <div class="card" style="margin-bottom: 20px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h3>🚗 Add Vehicle to Fedrix Fleet</h3>
                            <div style="display:flex; gap:10px;">
                                <input id="veh-name" type="text" placeholder="Name (e.g. Pegassi Terzo)" style="margin:0; width:180px;">
                                <input id="veh-plate" type="text" placeholder="Plate (FEDRIX17)" style="margin:0; width:140px;">
                                <input id="veh-rank" type="text" placeholder="Min Rank (e.g. 4)" style="margin:0; width:110px;">
                                <button class="btn btn-primary" onclick="addLibraVehicle()">+ Add Car</button>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>Fedrix Fleet ({len(vehicles)} Vehicles)</h3>
                        <table>
                            <thead>
                                <tr><th>ID</th><th>Vehicle Name</th><th>Plate</th><th>Rank Req</th><th>Insurance</th><th>Actions</th></tr>
                            </thead>
                            <tbody>{veh_rows}</tbody>
                        </table>
                    </div>
                </div>

                <!-- TAB 3: EVENTS -->
                <div id="tab-events" style="display:none;">
                    <div class="grid-2" style="margin-bottom:24px;">{event_cards}</div>
                </div>
            </main>

            <script>
                function showTab(tab) {{
                    document.getElementById('tab-bank').style.display = tab === 'bank' ? 'block' : 'none';
                    document.getElementById('tab-garage').style.display = tab === 'garage' ? 'block' : 'none';
                    document.getElementById('tab-events').style.display = tab === 'events' ? 'block' : 'none';
                    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                    event.target.classList.add('active');
                }}

                async function submitDeposit(server) {{
                    let amt = document.getElementById('dep-amt').value;
                    let reason = document.getElementById('dep-reason').value || "Web Deposit";
                    let res = await fetch('/api/bank/deposit', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ server, amount: amt, reason }})
                    }});
                    let d = await res.json();
                    if (d.success) {{ alert("Deposit successful!"); location.reload(); }}
                    else alert("Error: " + d.error);
                }}

                async function submitWithdraw(server) {{
                    let amt = document.getElementById('with-amt').value;
                    let reason = document.getElementById('with-reason').value || "Web Withdrawal";
                    let res = await fetch('/api/bank/withdraw', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ server, amount: amt, reason }})
                    }});
                    let d = await res.json();
                    if (d.success) {{ alert("Withdrawal logged!"); location.reload(); }}
                    else alert("Error: " + d.error);
                }}

                async function renewVehicle(id) {{
                    let res = await fetch('/api/vehicle/renew', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ identifier: id, days: 30 }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                    else alert(d.error);
                }}

                async function removeVehicle(id) {{
                    if (!confirm("Are you sure?")) return;
                    let res = await fetch('/api/vehicle/remove', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ identifier: id }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                }}

                async function addLibraVehicle() {{
                    let name = document.getElementById('veh-name').value;
                    let plate = document.getElementById('veh-plate').value;
                    let rank = document.getElementById('veh-rank').value || "1";
                    if (!name) return alert("Vehicle name required");
                    let res = await fetch('/api/vehicle/add', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ server: 'librarp', name, plate, notes: 'Rank ' + rank + '+ Required' }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                    else alert(d.error);
                }}

                async function removeEvent(id) {{
                    if (!confirm("Remove event?")) return;
                    let res = await fetch('/api/event/remove', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ event_id: id }})
                    }});
                    let d = await res.json();
                    if (d.success) location.reload();
                }}
            </script>
        </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

# ==========================================
# REST API HANDLERS
# ==========================================
def require_user(request: web.Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise web.HTTPUnauthorized(
            text=json.dumps({"success": False, "error": "Unauthorized. Please log in first."}),
            content_type="application/json"
        )
    return user

async def api_bank_deposit(request: web.Request):
    user = require_user(request)
    data = await request.json()
    server = data.get("server", "grandrp")
    try:
        gross = parse_amount(data.get("amount", "0"))
        if gross <= 0:
            return web.json_response({"success": False, "error": "Amount must be > 0"})
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)})

    tax = gross * 0.03 if server == "grandrp" else 0.0
    net = gross - tax
    reason = data.get("reason", "Web Deposit")

    db.record_bank_transaction(server, user["id"], user["username"], "deposit", gross, tax, net, reason)
    bal = db.get_bank_balance(server)
    return web.json_response({"success": True, "balance": bal["balance"], "net": net, "tax": tax})

async def api_bank_withdraw(request: web.Request):
    user = require_user(request)
    data = await request.json()
    server = data.get("server", "grandrp")
    try:
        gross = parse_amount(data.get("amount", "0"))
        if gross <= 0:
            return web.json_response({"success": False, "error": "Amount must be > 0"})
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)})

    tax = gross * 0.05 if server == "grandrp" else 0.0
    net = gross - tax
    reason = data.get("reason", "Web Withdrawal")

    db.record_bank_transaction(server, user["id"], user["username"], "withdraw", gross, tax, net, reason)
    bal = db.get_bank_balance(server)
    return web.json_response({"success": True, "balance": bal["balance"], "net": net, "tax": tax})

async def api_vehicle_add(request: web.Request):
    user = require_user(request)
    data = await request.json()
    server = data.get("server", "grandrp")
    name = data.get("name")
    plate = data.get("plate")
    days = data.get("insurance_days", 0)
    notes = data.get("notes", "")

    exp = datetime.now(timezone.utc) + timedelta(days=days) if days > 0 else None
    db.add_vehicle(server, name, plate, exp, notes, user["username"])
    return web.json_response({"success": True})

async def api_vehicle_renew(request: web.Request):
    require_user(request)
    data = await request.json()
    identifier = data.get("identifier")
    days = data.get("days", 30)
    exp = datetime.now(timezone.utc) + timedelta(days=days)
    success = db.renew_vehicle_insurance(identifier, exp)
    return web.json_response({"success": success})

async def api_vehicle_remove(request: web.Request):
    require_user(request)
    data = await request.json()
    identifier = data.get("identifier")
    success = db.remove_vehicle(identifier)
    return web.json_response({"success": success})

async def api_plantation_plant(request: web.Request):
    require_user(request)
    now = datetime.now(timezone.utc)
    db.set_plantation_planted(now, now + timedelta(hours=2), now + timedelta(hours=4), 0)
    return web.json_response({"success": True})

async def api_plantation_nourish(request: web.Request):
    require_user(request)
    state = db.get_plantation_state()
    if state.get("status") != "GROWING":
        return web.json_response({"success": False, "error": "No active plantation growing"})
    now = datetime.now(timezone.utc)
    db.update_plantation_nourish(now, now + timedelta(hours=2))
    return web.json_response({"success": True})

async def api_plantation_harvest(request: web.Request):
    user = require_user(request)
    data = await request.json()
    try:
        profit = parse_amount(data.get("profit", "0"))
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)})

    db.reset_plantation()
    if data.get("add_to_bank", True):
        tax = profit * 0.03
        net = profit - tax
        db.record_bank_transaction("grandrp", user["id"], user["username"], "deposit", profit, tax, net, "Pineapple Harvest Profit")

    return web.json_response({"success": True})

async def api_event_remove(request: web.Request):
    require_user(request)
    data = await request.json()
    success = db.remove_event(data.get("event_id"))
    return web.json_response({"success": success})

def create_web_app():
    app = web.Application()

    # Pages
    app.router.add_get("/", handle_home)
    app.router.add_get("/grand", handle_grand)
    app.router.add_get("/libra", handle_libra)

    # Auth
    app.router.add_get("/auth/login", handle_login)
    app.router.add_get("/auth/callback", handle_callback)
    app.router.add_get("/auth/logout", handle_logout)
    app.router.add_get("/auth/quick_login", handle_quick_login)

    # REST APIs
    app.router.add_post("/api/bank/deposit", api_bank_deposit)
    app.router.add_post("/api/bank/withdraw", api_bank_withdraw)
    app.router.add_post("/api/vehicle/add", api_vehicle_add)
    app.router.add_post("/api/vehicle/renew", api_vehicle_renew)
    app.router.add_post("/api/vehicle/remove", api_vehicle_remove)
    app.router.add_post("/api/plantation/plant", api_plantation_plant)
    app.router.add_post("/api/plantation/nourish", api_plantation_nourish)
    app.router.add_post("/api/plantation/harvest", api_plantation_harvest)
    app.router.add_post("/api/event/remove", api_event_remove)

    return app
