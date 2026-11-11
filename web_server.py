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
    --bg-dark: #090a0f;
    --card-bg: #11131a;
    --card-border: #1e222d;
    --accent: #ef4444; /* Thenga Hood Crimson Red */
    --accent-hover: #dc2626;
    --accent-glow: rgba(239, 68, 68, 0.4);
    --gold: #f59e0b; /* Parotta Gold */
    --tender-green: #22c55e; /* Fresh Coconut Green */
    --green-glow: rgba(34, 197, 94, 0.3);
    --cyan: #06b6d4; /* Coconut Straw Cyan */
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
    background: #0d0f17;
    border-bottom: 2px solid rgba(239, 68, 68, 0.25);
    padding: 14px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 25px rgba(0,0,0,0.5);
}
.brand {
    font-size: 19px;
    font-weight: 900;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
    letter-spacing: 0.5px;
}
.brand-badge {
    font-size: 11px;
    font-weight: 800;
    color: #ef4444;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.4);
    padding: 2px 10px;
    border-radius: 9999px;
    letter-spacing: 0.8px;
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
    font-weight: 800;
    font-size: 14px;
    border-radius: 8px;
    cursor: pointer;
    border: none;
    text-decoration: none;
    transition: all 0.2s;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.btn-primary { 
    background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); 
    color: #fff; 
    box-shadow: 0 4px 14px rgba(239, 68, 68, 0.35);
}
.btn-primary:hover { 
    background: linear-gradient(135deg, #f87171 0%, #dc2626 100%); 
    box-shadow: 0 0 20px var(--accent-glow); 
    transform: translateY(-1px);
}
.btn-green { background: linear-gradient(135deg, #22c55e 0%, #15803d 100%); color: white; }
.btn-green:hover { box-shadow: 0 0 15px var(--green-glow); }
.btn-red { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); color: white; }
.btn-purple { background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); color: white; }
.btn-secondary { background: #1c202c; color: white; border: 1px solid #2b3244; }
.btn-secondary:hover { background: #2b3244; }
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
    font-weight: 800;
    padding: 8px 18px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    letter-spacing: 0.5px;
}
.tab-btn.active { 
    background: rgba(239, 68, 68, 0.15); 
    color: #f87171; 
    border: 1px solid rgba(239, 68, 68, 0.45);
}
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 24px;
    box-shadow: 0 4px 25px rgba(0, 0, 0, 0.45);
}
.stat-val { font-size: 26px; font-weight: 900; color: #fff; margin-top: 4px; }
.stat-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; font-weight: 800; letter-spacing: 0.8px; }
input, select {
    width: 100%;
    background: #090a0f;
    border: 1px solid #232838;
    color: #fff;
    padding: 12px;
    border-radius: 8px;
    font-size: 14px;
    margin-top: 6px;
    margin-bottom: 16px;
    transition: border-color 0.2s, box-shadow 0.2s;
}
input:focus, select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 12px var(--accent-glow); }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--card-border); font-size: 14px; }
th { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 800; letter-spacing: 0.5px; }
.badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
.badge-green { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
.badge-purple { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; }
"""

def render_header(user: dict, subtitle: str = "") -> str:
    is_adm = is_admin_user(user)
    badge_html = (
        '<span class="badge badge-red" style="font-size: 11px; margin-left: 6px;">👑 FOUNDER / ADMIN</span>'
        if is_adm else
        '<span class="badge badge-green" style="font-size: 11px; margin-left: 6px;">MEMBER</span>'
    )
    sub_tag = (
        f'<span style="font-size:14px; color:#94a3b8; font-weight:600;">/ {subtitle}</span>'
        if subtitle else
        '<span class="brand-badge">MALAYALI CLUB</span>'
    )
    return f"""
    <header>
        <a href="/" class="brand">
            <img src="/logo.png" alt="Thenga Logo" style="height:36px; width:auto; object-fit:contain; filter:drop-shadow(0 2px 8px rgba(239,68,68,0.5));">
            <span>THENGA <span style="color:var(--accent);">NETWORK</span></span> {sub_tag}
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
            <body style="justify-content: center; align-items: center; text-align: center; padding: 20px; background: radial-gradient(circle at 50% 20%, rgba(239, 68, 68, 0.12) 0%, rgba(9, 10, 15, 1) 70%);">
                <div class="card" style="max-width: 500px; width: 100%; padding: 46px 36px; border: 1.5px solid rgba(239, 68, 68, 0.45); box-shadow: 0 16px 60px rgba(0, 0, 0, 0.8), 0 0 45px rgba(239, 68, 68, 0.18); border-radius: 22px;">
                    <div style="margin-bottom: 20px;">
                        <img src="/logo.png" alt="Thenga Network" style="max-width: 230px; width: 100%; height: auto; filter: drop-shadow(0 8px 30px rgba(239, 68, 68, 0.5));">
                    </div>
                    <h1 style="color: #fff; font-size: 24px; font-weight: 900; margin-bottom: 8px; letter-spacing: -0.5px; text-transform: uppercase;">
                        Thenga Network <span style="color: var(--accent);">Dashboard</span>
                    </h1>
                    <p style="color: var(--text-secondary); margin-bottom: 28px; font-size: 14px; line-height: 1.5;">
                        Integrated command center for <b style="color: #f87171;">Thenga Network Malayali Club</b>
                    </p>
                    <a href="/auth/login" class="btn" style="width: 100%; padding: 15px; font-size: 15px; font-weight: 800; background: #5865F2; color: #fff; border-radius: 10px; box-shadow: 0 4px 20px rgba(88, 101, 242, 0.45); text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 10px; transition: transform 0.15s, box-shadow 0.15s;">
                        <svg style="width: 22px; height: 22px; fill: currentColor;" viewBox="0 0 24 24"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0a12.64 12.64 0 0 0-.617-1.25a.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10.2 10.2 0 0 0 .372-.292a.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127a12.299 12.299 0 0 1-1.873.894a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028a19.839 19.839 0 0 0 6.002-3.03a.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418z"/></svg>
                        Login with Discord
                    </a>
                    <div style="margin-top: 22px; font-size: 12px; color: #64748b; display: flex; align-items: center; justify-content: center; gap: 6px;">
                        <span>🔒</span> Verified Thenga Network Members Only
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
    profile = db.get_user_profile(user["id"], user["username"])
    is_adm = is_admin_user(user)

    role_badge = (
        '<span class="badge badge-red" style="font-size: 11px; padding: 3px 10px;">👑 FOUNDER / COMMANDER</span>'
        if is_adm else
        '<span class="badge badge-green" style="font-size: 11px; padding: 3px 10px;">VERIFIED OPERATIVE</span>'
    )

    html = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Operations Hub • Thenga Network</title>
            <style>
                {COMMON_CSS}
                @media (max-width: 950px) {{
                    .hub-layout {{ grid-template-columns: 1fr !important; }}
                    .hub-grid {{ grid-template-columns: 1fr !important; }}
                }}
            </style>
        </head>
        <body>
            {render_header(user)}

            <main style="max-width: 1300px; margin: 32px auto; width: 100%; padding: 0 24px;">
                <div class="hub-layout" style="display: grid; grid-template-columns: 1fr 340px; gap: 30px; align-items: start;">
                    
                    <!-- LEFT COLUMN: OPERATIONS COMMAND & SERVER SELECTOR -->
                    <div>
                        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 28px;">
                            <img src="/logo.png" alt="Thenga Logo" style="width: 72px; height: auto; filter: drop-shadow(0 4px 16px rgba(239, 68, 68, 0.45));">
                            <div>
                                <div style="font-size: 11px; font-weight: 800; color: var(--accent); letter-spacing: 1.5px; text-transform: uppercase;">Thenga Network Malayali Club</div>
                                <h1 style="font-size: 28px; font-weight: 900; color: #fff; letter-spacing: -0.5px; margin-top: 2px;">FAMILY OPERATIONS COMMAND</h1>
                                <p style="color: var(--text-secondary); margin-top: 4px; font-size: 14px;">Select active GTA RP server operations dashboard</p>
                            </div>
                        </div>

                        <div class="hub-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                            <!-- Grand RP Card -->
                            <a href="/grand" style="text-decoration: none; color: inherit;">
                                <div class="card" style="cursor: pointer; transition: transform 0.2s, border-color 0.2s; border-color: #3b82f6; height: 100%; display: flex; flex-direction: column; justify-content: space-between;" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='none'">
                                    <div>
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                                            <span style="font-size: 32px;">🌆</span>
                                            <span class="badge badge-green">3% / 5% Tax</span>
                                        </div>
                                        <h2 style="font-size: 24px; color: #60a5fa; margin-bottom: 8px; font-weight: 900;">Grand RP (EN2)</h2>
                                        <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
                                            Manage Family Fund, 31 Vehicles, and Pineapple Plantation Business.
                                        </p>
                                    </div>
                                    <div style="border-top: 1px solid var(--card-border); padding-top: 16px; display: flex; justify-content: space-between;">
                                        <div>
                                            <div class="stat-label">Treasury</div>
                                            <div style="font-weight: 800; color: #22c55e; font-size: 16px;">{format_money(grand_bal['balance'])}</div>
                                        </div>
                                        <div>
                                            <div class="stat-label">Fleet</div>
                                            <div style="font-weight: 800; color: #fff; font-size: 16px;">{len(grand_v)} Cars</div>
                                        </div>
                                        <div>
                                            <div class="stat-label">Plantation</div>
                                            <div style="font-weight: 800; color: #34d399; font-size: 16px;">Pineapple</div>
                                        </div>
                                    </div>
                                </div>
                            </a>

                            <!-- Libra RP Card -->
                            <a href="/libra" style="text-decoration: none; color: inherit;">
                                <div class="card" style="cursor: pointer; transition: transform 0.2s, border-color 0.2s; border-color: #a855f7; height: 100%; display: flex; flex-direction: column; justify-content: space-between;" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='none'">
                                    <div>
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                                            <span style="font-size: 32px;">⚖️</span>
                                            <span class="badge badge-purple">0% Tax • Active</span>
                                        </div>
                                        <h2 style="font-size: 24px; color: #c084fc; margin-bottom: 8px; font-weight: 900;">Libra RP (Fedrix)</h2>
                                        <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
                                            Manage Fedrix Clan Bank, 24 Vehicles, and Daily Events Radar.
                                        </p>
                                    </div>
                                    <div style="border-top: 1px solid var(--card-border); padding-top: 16px; display: flex; justify-content: space-between;">
                                        <div>
                                            <div class="stat-label">Treasury</div>
                                            <div style="font-weight: 800; color: #22c55e; font-size: 16px;">{format_money(libra_bal['balance'])}</div>
                                        </div>
                                        <div>
                                            <div class="stat-label">Fleet</div>
                                            <div style="font-weight: 800; color: #fff; font-size: 16px;">{len(libra_v)} Cars</div>
                                        </div>
                                        <div>
                                            <div class="stat-label">Events</div>
                                            <div style="font-weight: 800; color: #c084fc; font-size: 16px;">3 Scheduled</div>
                                        </div>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>

                    <!-- RIGHT COLUMN: VERTICAL USER INFO & IN-GAME RANKS TAB -->
                    <aside class="card" style="border: 1.5px solid rgba(239, 68, 68, 0.35); box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                        <!-- User Avatar & Identity -->
                        <div style="text-align: center; padding-bottom: 20px; border-bottom: 1px solid var(--card-border);">
                            <div style="position: relative; display: inline-block; margin-bottom: 12px;">
                                <img src="{user['avatar_url']}" style="width: 76px; height: 76px; border-radius: 50%; border: 2.5px solid var(--accent); box-shadow: 0 0 20px var(--accent-glow);">
                                <span style="position: absolute; bottom: 2px; right: 2px; width: 14px; height: 14px; background: #22c55e; border: 2.5px solid var(--card-bg); border-radius: 50%;"></span>
                            </div>
                            <h3 style="color: #fff; font-size: 18px; font-weight: 900; margin-bottom: 6px;">{user['username']}</h3>
                            {role_badge}
                        </div>

                        <!-- In-Game Ranks Vertical Section -->
                        <div style="padding-top: 20px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                                <span class="stat-label" style="font-size: 11px;">IN-GAME DOSSIER</span>
                                <button onclick="toggleEditRanks()" style="background: none; border: none; color: var(--accent); font-size: 12px; font-weight: 800; cursor: pointer; display: flex; align-items: center; gap: 4px;">
                                    ✏️ Edit Ranks
                                </button>
                            </div>

                            <!-- Grand RP Rank -->
                            <div style="background: #090a0f; border: 1px solid #1e222d; border-left: 3px solid #3b82f6; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                    <span style="font-size: 12px; font-weight: 800; color: #60a5fa;">🌆 Grand RP (EN2)</span>
                                    <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #93c5fd; font-size: 10px; padding: 2px 6px;">EN2 Family</span>
                                </div>
                                <div id="grand-rank-display" style="font-size: 14px; font-weight: 800; color: #fff; margin-top: 2px;">{profile['grand_rank']}</div>
                            </div>

                            <!-- Libra RP Rank -->
                            <div style="background: #090a0f; border: 1px solid #1e222d; border-left: 3px solid #a855f7; border-radius: 10px; padding: 14px; margin-bottom: 16px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                    <span style="font-size: 12px; font-weight: 800; color: #c084fc;">⚖️ Libra RP (Fedrix)</span>
                                    <span class="badge" style="background: rgba(168, 85, 247, 0.15); color: #d8b4fe; font-size: 10px; padding: 2px 6px;">Fedrix Clan</span>
                                </div>
                                <div id="libra-rank-display" style="font-size: 14px; font-weight: 800; color: #fff; margin-top: 2px;">{profile['libra_rank']}</div>
                            </div>

                            <!-- Rank Edit Form (Hidden by default) -->
                            <div id="rank-edit-box" style="display: none; background: #0c0e15; border: 1px dashed var(--accent); border-radius: 10px; padding: 14px; margin-bottom: 16px;">
                                <label style="font-size: 11px; font-weight: 800; color: var(--text-secondary); text-transform: uppercase;">Grand RP Rank:</label>
                                <input id="input-grand-rank" type="text" value="{profile['grand_rank']}" style="padding: 8px 12px; font-size: 13px; margin: 4px 0 10px;">
                                
                                <label style="font-size: 11px; font-weight: 800; color: var(--text-secondary); text-transform: uppercase;">Libra RP Rank:</label>
                                <input id="input-libra-rank" type="text" value="{profile['libra_rank']}" style="padding: 8px 12px; font-size: 13px; margin: 4px 0 12px;">
                                
                                <div style="display: flex; gap: 8px;">
                                    <button class="btn btn-primary" style="flex: 1; padding: 8px; font-size: 12px;" onclick="saveUserRanks()">Save</button>
                                    <button class="btn btn-secondary" style="padding: 8px 12px; font-size: 12px;" onclick="toggleEditRanks()">Cancel</button>
                                </div>
                            </div>

                            <!-- Quick Stats -->
                            <div style="border-top: 1px solid var(--card-border); padding-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; text-align: center;">
                                <div>
                                    <div class="stat-label" style="font-size: 10px;">Network Funds</div>
                                    <div style="font-size: 15px; font-weight: 800; color: #22c55e; margin-top: 2px;">{format_money(grand_bal['balance'] + libra_bal['balance'])}</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size: 10px;">Active Fleet</div>
                                    <div style="font-size: 15px; font-weight: 800; color: #fff; margin-top: 2px;">{len(grand_v) + len(libra_v)} Cars</div>
                                </div>
                            </div>
                        </div>
                    </aside>
                </div>
            </main>

            <script>
                function toggleEditRanks() {{
                    var box = document.getElementById('rank-edit-box');
                    box.style.display = box.style.display === 'none' ? 'block' : 'none';
                }}

                async function saveUserRanks() {{
                    var grand = document.getElementById('input-grand-rank').value;
                    var libra = document.getElementById('input-libra-rank').value;
                    try {{
                        var res = await fetch('/api/user/rank', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{grand_rank: grand, libra_rank: libra}})
                        }});
                        var data = await res.json();
                        if (data.success) {{
                            document.getElementById('grand-rank-display').innerText = data.grand_rank;
                            document.getElementById('libra-rank-display').innerText = data.libra_rank;
                            toggleEditRanks();
                        }} else {{
                            alert(data.error || 'Failed to update ranks');
                        }}
                    }} catch (e) {{
                        alert('Error saving ranks: ' + e);
                    }}
                }}
            </script>
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
                            <div class="stat-val" style="color:#22c55e;">{format_money(bal['balance'])}</div>
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

async def api_update_user_rank(request: web.Request):
    user = require_user(request)
    data = await request.json()
    grand_rank = data.get("grand_rank", "").strip() or "Member (Rank 1)"
    libra_rank = data.get("libra_rank", "").strip() or "Associate (Rank 1)"
    db.update_user_ranks(user["id"], grand_rank, libra_rank)
    return web.json_response({"success": True, "grand_rank": grand_rank, "libra_rank": libra_rank})

async def handle_logo(request: web.Request):
    logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")
    if os.path.exists(logo_path):
        return web.FileResponse(logo_path)
    return web.Response(status=404)

def create_web_app():
    app = web.Application()

    # Assets & Pages
    app.router.add_get("/logo.png", handle_logo)
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
    app.router.add_post("/api/user/rank", api_update_user_rank)

    return app
