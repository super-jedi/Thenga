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
table { width: 100%; border-collapse: collapse; }
.table-responsive {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin-top: 10px;
    border-radius: 8px;
}
th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--card-border); font-size: 14px; white-space: nowrap; }
th { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 800; letter-spacing: 0.5px; }
.badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
.badge-green { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
.badge-purple { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; }

/* GTA V LICENSE PLATES */
.gtav-plate {
    display: inline-block;
    background: #0f121b;
    border: 1.5px solid #f59e0b;
    color: #f59e0b;
    font-family: 'Courier New', Courier, monospace;
    font-weight: 900;
    font-size: 13px;
    letter-spacing: 2px;
    padding: 3px 8px;
    border-radius: 4px;
    box-shadow: inset 0 0 6px rgba(245, 158, 11, 0.25);
    text-transform: uppercase;
}
.gtav-plate-sm {
    display: inline-block;
    background: #0f121b;
    border: 1px solid #f59e0b;
    color: #f59e0b;
    font-family: 'Courier New', Courier, monospace;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 1.5px;
    padding: 1px 6px;
    border-radius: 3px;
    text-transform: uppercase;
}

/* GRAND RP SHOWROOM FLEET GRID */
.grand-veh-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 16px;
    margin-top: 16px;
}
.grand-veh-card {
    background: #0d0f17;
    border: 1px solid #1a1e2b;
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    position: relative;
}
.grand-veh-card:hover {
    transform: translateY(-4px);
    border-color: #3b82f6;
    box-shadow: 0 8px 24px rgba(0,0,0,0.6);
}
.grand-veh-thumb-wrap {
    position: relative;
    height: 135px;
    background: radial-gradient(circle at center, #1e293b 0%, #07090e 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px;
    overflow: hidden;
    border-bottom: 1px solid #1a1e2b;
}
.grand-veh-img {
    max-height: 110px;
    max-width: 90%;
    object-fit: contain;
    filter: drop-shadow(0 6px 14px rgba(0,0,0,0.85));
    transition: transform 0.25s ease;
}
.grand-veh-card:hover .grand-veh-img {
    transform: scale(1.06);
}
.grand-veh-id-badge {
    position: absolute;
    top: 8px;
    left: 8px;
    background: rgba(0,0,0,0.75);
    border: 1px solid rgba(255,255,255,0.15);
    color: #94a3b8;
    font-size: 11px;
    font-weight: 800;
    padding: 2px 8px;
    border-radius: 6px;
    backdrop-filter: blur(4px);
}
.grand-veh-status-badge {
    position: absolute;
    top: 8px;
    right: 8px;
}
.grand-veh-info {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    flex: 1;
    justify-content: space-between;
}
.grand-veh-name {
    font-size: 15px;
    font-weight: 800;
    color: #fff;
    margin-bottom: 6px;
}
.grand-veh-plate-wrap {
    margin-bottom: 8px;
}
.grand-veh-notes {
    font-size: 12px;
    color: #64748b;
    margin-bottom: 14px;
    min-height: 18px;
}
.grand-veh-actions {
    display: flex;
    gap: 8px;
    margin-top: auto;
}
.btn-sm {
    padding: 6px 10px !important;
    font-size: 11px !important;
    flex: 1;
}

/* RESPONSIVE MEDIA QUERIES FOR MOBILE */
@media (max-width: 768px) {
    header {
        padding: 10px 16px;
        flex-wrap: wrap;
        gap: 10px;
    }
    .brand { font-size: 16px; }
    .brand-badge { display: none; }
    .user-pill { padding: 4px 10px; font-size: 13px; }
    .user-avatar { width: 26px; height: 26px; }
    .tabs {
        overflow-x: auto;
        white-space: nowrap;
        -webkit-overflow-scrolling: touch;
        padding-bottom: 8px;
        gap: 8px;
    }
    .tab-btn { padding: 6px 12px; font-size: 13px; }
    .grid-2, .grid-3 { grid-template-columns: 1fr !important; }
    .card { padding: 16px; border-radius: 12px; }
    .stat-val { font-size: 20px; }
    .grand-veh-grid { grid-template-columns: 1fr !important; }
}
@media (max-width: 480px) {
    header { padding: 8px 12px; }
    .brand span { font-size: 14px; }
    main { padding: 0 10px !important; }
}
"""

def render_header(user: dict, subtitle: str = "") -> str:
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
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    members = db.get_libra_members()
    profile = db.get_user_profile(user["id"], user["username"])
    is_adm = is_admin_user(user)
    is_first_time = (
        profile.get("profile_completed") != 1 and
        profile.get("libra_member_id") is None and
        not profile.get("grand_member_name")
    )

    # First time member dropdown options
    member_select_options = '<option value="">-- Choose your in-game character --</option>'
    for m in members:
        is_claimed = bool(m.get("discord_id"))
        suffix = f" (Claimed by @{m['discord_username']})" if is_claimed else ""
        selected = 'selected' if profile.get('libra_member_id') == m['id'] else ''
        mid = m['id']
        mname = m['name']
        mlvl = m['rank_level']
        mrname = m['rank_name']
        member_select_options += f'<option value="{mid}" {selected}>{mname} (ID {mid} • Lv {mlvl} {mrname}){suffix}</option>'
    member_select_options += '<option value="0">I am a new recruit / not on this roster</option>'

    role_badge = (
        '<span class="badge badge-red" style="font-size: 11px; padding: 3px 10px;">👑 FOUNDER / COMMANDER</span>'
        if is_adm else
        '<span class="badge badge-green" style="font-size: 11px; padding: 3px 10px;">VERIFIED OPERATIVE</span>'
    )

    html = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Operations Hub • Thenga Network</title>
            <style>
                {COMMON_CSS}
                @media (max-width: 950px) {{
                    .hub-layout {{ grid-template-columns: 1fr !important; }}
                    .hub-grid {{ grid-template-columns: 1fr !important; }}
                }}
                @media (max-width: 600px) {{
                    main {{ padding: 0 12px !important; margin: 16px auto !important; }}
                    .hub-layout {{ gap: 20px !important; }}
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

                        <div class="hub-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;">
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

                            <!-- Discord Management Card -->
                            <div class="card" style="border-color: #5865F2; height: 100%; display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.2s, border-color 0.2s;" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='none'">
                                <div>
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                                        <span style="font-size: 32px;">🎮</span>
                                        <span class="badge" style="background: rgba(88, 101, 242, 0.2); color: #818cf8; border: 1px solid #5865F2;">Active Server</span>
                                    </div>
                                    <h2 style="font-size: 24px; color: #818cf8; margin-bottom: 8px; font-weight: 900;">Discord Management</h2>
                                    <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">
                                        High Command Discord Operations, Clan Moderation, and Bot Infrastructure.
                                    </p>
                                </div>
                                <div style="border-top: 1px solid var(--card-border); padding-top: 16px; display: flex; justify-content: space-between;">
                                    <div>
                                        <div class="stat-label">Bot Status</div>
                                        <div style="font-weight: 800; color: #22c55e; font-size: 16px;">ONLINE</div>
                                    </div>
                                    <div>
                                        <div class="stat-label">Disciplinary</div>
                                        <div style="font-weight: 800; color: #f59e0b; font-size: 16px;">Isolated</div>
                                    </div>
                                    <div>
                                        <div class="stat-label">Commands</div>
                                        <div style="font-weight: 800; color: #818cf8; font-size: 16px;">/libra /grp</div>
                                    </div>
                                </div>
                            </div>
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
                            <div style="border-top: 1px solid var(--card-border); padding-top: 16px; margin-bottom: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; text-align: center;">
                                <div>
                                    <div class="stat-label" style="font-size: 10px;">Network Funds</div>
                                    <div style="font-size: 15px; font-weight: 800; color: #22c55e; margin-top: 2px;">{format_money(grand_bal['balance'] + libra_bal['balance'])}</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size: 10px;">Active Fleet</div>
                                    <div style="font-size: 15px; font-weight: 800; color: #fff; margin-top: 2px;">{len(grand_v) + len(libra_v)} Cars</div>
                                </div>
                            </div>

                            <button onclick="openProfileModal()" class="btn btn-primary" style="width: 100%; padding: 10px; font-size: 12px; background: linear-gradient(135deg, #ef4444 0%, #a855f7 100%);">
                                🔗 Connect In-Game Personas
                            </button>
                        </div>
                    </aside>
                </div>
            </main>

            <!-- FIRST-TIME / LINK PROFILE MODAL -->
            <div id="profileModal" style="display: {"flex" if is_first_time else "none"}; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.75); backdrop-filter: blur(6px); z-index: 9999; justify-content: center; align-items: center; padding: 20px;">
                <div class="card" style="max-width: 500px; width: 100%; border: 1.5px solid var(--accent); box-shadow: 0 16px 50px rgba(0,0,0,0.85); border-radius: 16px;">
                    <div style="text-align: center; margin-bottom: 18px;">
                        <img src="/logo.png" style="width: 64px; height: auto; filter: drop-shadow(0 4px 12px rgba(239,68,68,0.5));">
                        <h2 style="color: #fff; font-size: 20px; font-weight: 900; margin-top: 10px; text-transform: uppercase;">
                            Connect Your In-Game Operatives
                        </h2>
                        <p style="color: #94a3b8; font-size: 13px; margin-top: 4px;">
                            Link your Discord account to your Grand RP & Libra RP characters
                        </p>
                    </div>

                    <!-- Libra RP Select -->
                    <div style="background: #090a0f; border: 1px solid #1a1e2b; border-left: 3px solid #a855f7; border-radius: 8px; padding: 12px; margin-bottom: 14px;">
                        <label style="font-size: 11px; font-weight: 800; color: #c084fc; text-transform: uppercase;">⚖️ Libra RP (Fedrix Clan Character):</label>
                        <select id="link-libra-id" style="margin-top: 6px; margin-bottom: 4px;">
                            {member_select_options}
                        </select>
                        <span style="font-size: 11px; color: #64748b;">Select your in-game clan identity from the 28 seeded members</span>
                    </div>

                    <!-- Grand RP Input -->
                    <div style="background: #090a0f; border: 1px solid #1a1e2b; border-left: 3px solid #3b82f6; border-radius: 8px; padding: 12px; margin-bottom: 20px;">
                        <label style="font-size: 11px; font-weight: 800; color: #60a5fa; text-transform: uppercase;">🌆 Grand RP (EN2 Character):</label>
                        <input id="link-grand-name" type="text" value="{profile.get('grand_member_name') or user['username']}" placeholder="Character Name (e.g. Haris Thenga)" style="margin-top: 6px; margin-bottom: 8px;">
                        
                        <label style="font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase;">Grand RP Rank:</label>
                        <select id="link-grand-rank" style="margin-top: 4px; margin-bottom: 4px;">
                            <option value="Family Member (Rank 1)">Family Member (Rank 1)</option>
                            <option value="Enforcer (Rank 3)">Enforcer (Rank 3)</option>
                            <option value="High Command (Rank 7)">High Command (Rank 7)</option>
                            <option value="Co-Leader (Rank 9)">Co-Leader (Rank 9)</option>
                            <option value="Leader / Boss (Rank 10)">Leader / Boss (Rank 10)</option>
                        </select>
                    </div>

                    <div style="display: flex; gap: 10px;">
                        <button id="btn-save-personas" class="btn btn-primary" style="flex: 1; padding: 12px;" onclick="submitLinkProfiles(this)">Save & Link Personas</button>
                        <button class="btn btn-secondary" onclick="dismissProfileModal()">Later</button>
                    </div>
                </div>
            </div>

            <script>
                // Instant suppression if modal was already dismissed or saved
                if (localStorage.getItem('thenga_profile_dismissed') === 'true') {{
                    var pm = document.getElementById('profileModal');
                    if (pm) pm.style.display = 'none';
                }}

                function dismissProfileModal() {{
                    localStorage.setItem('thenga_profile_dismissed', 'true');
                    closeModal('profileModal');
                    fetch('/api/user/dismiss_profile_prompt', {{ method: 'POST' }}).catch(() => {{}});
                }}

                function toggleEditRanks() {{
                    var box = document.getElementById('rank-edit-box');
                    box.style.display = box.style.display === 'none' ? 'block' : 'none';
                }}

                function openProfileModal() {{
                    document.getElementById('profileModal').style.display = 'flex';
                }}

                function closeModal(id) {{
                    document.getElementById(id).style.display = 'none';
                }}

                async function submitLinkProfiles(btn) {{
                    let targetBtn = btn || document.getElementById('btn-save-personas');
                    let oldText = targetBtn ? targetBtn.innerText : "Save & Link Personas";
                    if (targetBtn) {{
                        targetBtn.innerText = "⏳ Saving...";
                        targetBtn.disabled = true;
                    }}

                    try {{
                        let libraEl = document.getElementById('link-libra-id');
                        let grandEl = document.getElementById('link-grand-name');
                        let rankEl = document.getElementById('link-grand-rank');
                        
                        let libraId = libraEl ? libraEl.value : '';
                        let grandName = grandEl ? grandEl.value : '';
                        let grandRank = rankEl ? rankEl.value : '';

                        let res = await fetch('/api/user/link_profiles', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{ libra_member_id: libraId, grand_name: grandName, grand_rank: grandRank }})
                        }});
                        let d = await res.json();
                        if (d.success) {{
                            localStorage.setItem('thenga_profile_dismissed', 'true');
                            if (targetBtn) targetBtn.innerText = "✓ Linked!";
                            alert("In-game personas successfully linked!");
                            location.reload();
                        }} else {{
                            alert("Error: " + (d.error || "Failed to link personas"));
                            if (targetBtn) {{
                                targetBtn.innerText = oldText;
                                targetBtn.disabled = false;
                            }}
                        }}
                    }} catch (err) {{
                        alert("Network or server error: " + err);
                        if (targetBtn) {{
                            targetBtn.innerText = oldText;
                            targetBtn.disabled = false;
                        }}
                    }}
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

    # Build vehicles cards & table rows
    now = datetime.now(timezone.utc)
    veh_rows = ""
    veh_grid_cards = ""
    for v in vehicles:
        v_id = v["id"]
        v_img = v.get("image_url") or (f"/static/vehicles/grand_veh_{v_id}.png" if v_id <= 31 else "/logo.png")
        plate = v.get("plate") or "NO PLATE"
        has_plate = bool(v.get("plate"))
        exp = v.get("insurance_expiry")
        is_exp = True
        exp_txt = "EXPIRED"
        if exp:
            exp_dt = datetime.fromisoformat(exp)
            if now < exp_dt:
                is_exp = False
                exp_txt = exp_dt.strftime("%Y-%m-%d")

        badge = '<span class="badge badge-red">EXPIRED</span>' if is_exp else f'<span class="badge badge-green">{exp_txt}</span>'
        plate_badge = f'<span class="gtav-plate">{plate}</span>' if has_plate else '<span style="color:#64748b; font-size:12px; font-style:italic;">No Plate</span>'
        plate_badge_sm = f'<span class="gtav-plate-sm">{plate}</span>' if has_plate else '<span style="color:#64748b; font-size:11px; font-style:italic;">No Plate</span>'

        # Showroom Grid Card
        veh_grid_cards += f"""
        <div class="grand-veh-card">
            <div class="grand-veh-thumb-wrap">
                <span class="grand-veh-id-badge">#{v_id}</span>
                <span class="grand-veh-status-badge">{badge}</span>
                <img src="{v_img}" alt="{v['name']}" class="grand-veh-img" onerror="this.src='/logo.png'">
            </div>
            <div class="grand-veh-info">
                <div>
                    <div class="grand-veh-name">{v['name']}</div>
                    <div class="grand-veh-plate-wrap">{plate_badge}</div>
                    <div class="grand-veh-notes">{v.get('notes') or 'Family Fleet Vehicle'}</div>
                </div>
                <div class="grand-veh-actions">
                    <button class="btn btn-primary btn-sm" onclick="renewVehicle('{v_id}')">🛡️ +30d Insurance</button>
                    <button class="btn btn-red btn-sm" style="flex:0 0 38px;" onclick="removeVehicle('{v_id}')" title="Remove Vehicle">🗑️</button>
                </div>
            </div>
        </div>
        """

        # Table Row with thumbnail
        veh_rows += f"""
        <tr>
            <td><b>#{v_id}</b></td>
            <td>
                <div style="display:flex; align-items:center; gap:12px;">
                    <img src="{v_img}" style="width:58px; height:34px; object-fit:contain; background:#080a0f; border-radius:6px; border:1px solid #1e2436; padding:2px;" onerror="this.src='/logo.png'">
                    <b>{v['name']}</b>
                </div>
            </td>
            <td>{plate_badge_sm}</td>
            <td>{v.get('notes') or '-'}</td>
            <td>{badge}</td>
            <td>
                <button class="btn btn-primary" style="padding: 4px 10px; font-size: 12px;" onclick="renewVehicle('{v_id}')">🛡️ +30d</button>
                <button class="btn btn-red" style="padding: 4px 10px; font-size: 12px;" onclick="removeVehicle('{v_id}')">🗑️</button>
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
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Grand RP (EN2) • Thenga Network</title>
            <style>
                {COMMON_CSS}
                @media (max-width: 600px) {{
                    main {{ padding: 0 12px !important; margin: 16px auto !important; }}
                }}
            </style>
        </head>
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
                    <button id="tab-btn-bank" class="tab-btn active" onclick="showTab('bank')">🏦 Family Treasury</button>
                    <button id="tab-btn-garage" class="tab-btn" onclick="showTab('garage')">🏎️ Garage Fleet ({len(vehicles)})</button>
                    <button id="tab-btn-plantation" class="tab-btn" onclick="showTab('plantation')">🍍 Pineapple Plantation</button>
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
                        <h3 style="margin-bottom: 12px;">📜 Recent Grand RP Transactions</h3>
                        <div class="table-responsive">
                            <table>
                                <thead>
                                    <tr><th>Type</th><th>Gross</th><th>Tax</th><th>Net</th><th>Member</th><th>Reason</th><th>Date</th></tr>
                                </thead>
                                <tbody>{tx_rows}</tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- TAB 2: GARAGE -->
                <div id="tab-garage" style="display:none;">
                    <div class="card" style="margin-bottom: 20px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
                            <div>
                                <h3 style="margin:0;">🚗 Add Vehicle to Grand RP</h3>
                                <div style="color:var(--text-secondary); font-size:12px; margin-top:2px;">Register a new vehicle with insurance duration</div>
                            </div>
                            <div style="display:flex; flex-wrap:wrap; gap:10px; flex:1; max-width:600px; justify-content:flex-end;">
                                <input id="veh-name" type="text" placeholder="Vehicle Name (e.g. Chiron)" style="margin:0; flex:2; min-width:140px;">
                                <input id="veh-plate" type="text" placeholder="Plate (optional)" style="margin:0; flex:1; min-width:100px;">
                                <input id="veh-days" type="number" placeholder="Days (0=Exp)" style="margin:0; flex:1; min-width:90px;">
                                <button class="btn btn-primary" onclick="addVehicle('grandrp')">+ Add Car</button>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:16px;">
                            <div>
                                <h3 style="margin:0;">Grand RP Fleet ({len(vehicles)} Vehicles)</h3>
                                <div style="color:var(--text-secondary); font-size:13px; margin-top:2px;">Authentic GTA V GrandRP fleet renders & registered license plates</div>
                            </div>
                            <div style="display:flex; gap:8px;">
                                <button id="btn-view-grid" class="tab-btn active" style="padding:6px 14px; font-size:12px; border:1px solid rgba(59,130,246,0.4);" onclick="setGarageView('grid')">🎴 Showroom Grid</button>
                                <button id="btn-view-table" class="tab-btn" style="padding:6px 14px; font-size:12px; border:1px solid #2b3244;" onclick="setGarageView('table')">📋 Table View</button>
                            </div>
                        </div>

                        <!-- SHOWROOM GRID VIEW -->
                        <div id="garage-grid-view" class="grand-veh-grid">
                            {veh_grid_cards}
                        </div>

                        <!-- TABLE VIEW -->
                        <div id="garage-table-view" class="table-responsive" style="display:none;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Vehicle Name</th>
                                        <th>Plate</th>
                                        <th>Notes</th>
                                        <th>Insurance Status</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>{veh_rows}</tbody>
                            </table>
                        </div>
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
                        <div style="display:flex; flex-wrap:wrap; gap:12px;">
                            <button class="btn btn-green" onclick="plantCrop()">🌱 Plant Pineapple (2h nourish, 4h harvest)</button>
                            <button class="btn btn-primary" onclick="nourishCrop()">💧 Nourish Now (+2h)</button>
                            <button class="btn btn-purple" onclick="harvestCrop()">🚜 Collect Harvest & Bank</button>
                        </div>
                    </div>
                </div>
            </main>

            <script>
                function setGarageView(view) {{
                    var gView = document.getElementById('garage-grid-view');
                    var tView = document.getElementById('garage-table-view');
                    var btnGrid = document.getElementById('btn-view-grid');
                    var btnTable = document.getElementById('btn-view-table');

                    if (view === 'grid') {{
                        if (gView) gView.style.display = 'grid';
                        if (tView) tView.style.display = 'none';
                        if (btnGrid) {{ btnGrid.classList.add('active'); btnGrid.style.borderColor = 'rgba(59,130,246,0.5)'; }}
                        if (btnTable) {{ btnTable.classList.remove('active'); btnTable.style.borderColor = '#2b3244'; }}
                        localStorage.setItem('grand_garage_view', 'grid');
                    }} else {{
                        if (gView) gView.style.display = 'none';
                        if (tView) tView.style.display = 'block';
                        if (btnGrid) {{ btnGrid.classList.remove('active'); btnGrid.style.borderColor = '#2b3244'; }}
                        if (btnTable) {{ btnTable.classList.add('active'); btnTable.style.borderColor = 'rgba(59,130,246,0.5)'; }}
                        localStorage.setItem('grand_garage_view', 'table');
                    }}
                }}

                if (localStorage.getItem('grand_garage_view') === 'table') {{
                    setGarageView('table');
                }}

                function showTab(tab) {{
                    document.getElementById('tab-bank').style.display = tab === 'bank' ? 'block' : 'none';
                    document.getElementById('tab-garage').style.display = tab === 'garage' ? 'block' : 'none';
                    document.getElementById('tab-plantation').style.display = tab === 'plantation' ? 'block' : 'none';
                    
                    document.getElementById('tab-btn-bank').classList.toggle('active', tab === 'bank');
                    document.getElementById('tab-btn-garage').classList.toggle('active', tab === 'garage');
                    document.getElementById('tab-btn-plantation').classList.toggle('active', tab === 'plantation');
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
# PAGE 3: LIBRA RP DASHBOARD (/libra) - AUTHENTIC IN-GAME CLAN UI
# ==========================================
async def handle_libra(request: web.Request):
    user = get_current_user(request)
    if not user:
        return web.HTTPFound("/")

    bal = db.get_bank_balance("librarp")
    txs = db.get_recent_transactions("librarp", limit=30)
    vehicles = db.get_vehicles("librarp")
    events = db.get_events("librarp")
    members = db.get_libra_members()
    ranks = db.get_libra_ranks()
    profile = db.get_user_profile(user["id"], user["username"])
    
    can_manage = db.user_can_manage_libra(user)
    is_founder = is_admin_user(user)
    is_first_time = (
        profile.get("profile_completed") != 1 and
        profile.get("libra_member_id") is None and
        not profile.get("grand_member_name")
    )

    # 1. Build Members Table Rows
    member_rows = ""
    for m in members:
        discord_badge = ""
        if m.get("discord_username"):
            discord_badge = f'<span class="badge" style="background:rgba(88,101,242,0.18); color:#818cf8; border:1px solid rgba(88,101,242,0.4); font-size:10px; margin-left:8px; padding:1px 6px;">@{m["discord_username"]}</span>'
        
        # Determine if viewer can manage this member (strictly higher rank or founder)
        can_edit_this = is_founder or db.user_can_manage_libra(user, m["rank_level"])
        
        mid = m['id']
        mlvl = m['rank_level']
        mrname = m['rank_name']
        safe_name = m['name'].replace("'", "\\'")
        w_cnt = m.get('warnings') or 0

        if w_cnt == 0:
            warn_badge = f'<span class="badge badge-green" style="font-size:11px; cursor:pointer;" onclick="openWarnModal({mid}, \'{safe_name}\', {w_cnt})">0/3 CLEAN</span>'
        elif w_cnt == 1:
            warn_badge = f'<span class="badge" style="background:rgba(245,158,11,0.2); color:#fbbf24; border:1px solid #f59e0b; font-size:11px; cursor:pointer;" onclick="openWarnModal({mid}, \'{safe_name}\', {w_cnt})">⚠️ 1/3 WARN</span>'
        elif w_cnt == 2:
            warn_badge = f'<span class="badge" style="background:rgba(239,68,68,0.2); color:#f87171; border:1px solid #ef4444; font-size:11px; cursor:pointer;" onclick="openWarnModal({mid}, \'{safe_name}\', {w_cnt})">⚠️ 2/3 FINAL</span>'
        else:
            warn_badge = f'<span class="badge badge-red" style="font-size:11px; cursor:pointer;" onclick="openWarnModal({mid}, \'{safe_name}\', {w_cnt})">🚨 {w_cnt}/3 STRIKE</span>'

        actions_html = ""
        if can_edit_this:
            actions_html = f'''
            <button class="ingame-btn-action" onclick="openRankModal({mid}, '{safe_name}', {mlvl}, '{mrname}')">RANK</button>
            <button class="ingame-btn-action btn-warn" onclick="openWarnModal({mid}, '{safe_name}', {w_cnt})">WARN</button>
            <button class="ingame-btn-action btn-kick" onclick="openKickModal({mid}, '{safe_name}', {mlvl})">KICK</button>
            '''
        elif not m.get("discord_id") and is_first_time:
            actions_html = f'''
            <button class="ingame-btn-claim" onclick="claimLibraProfile({mid}, '{safe_name}')">CLAIM</button>
            '''

        member_rows += f'''
        <tr class="member-row" data-id="{mid}" data-name="{m['name'].lower()}">
            <td>
                <div style="display:flex; align-items:center;">
                    <span style="color:#fff; font-weight:700; font-size:15px;">{m['name']}</span>
                    {discord_badge}
                </div>
            </td>
            <td>
                <code style="background:#0e111a; border:1px solid #232838; padding:3px 8px; border-radius:4px; color:#cbd5e1; font-weight:700; font-size:13px;">#{mid}</code>
            </td>
            <td>
                <span style="color:#94a3b8; font-size:13px; font-weight:700;">Lv {mlvl}</span>
                <span style="color:#ffffff; font-weight:800; font-size:14px; margin-left:6px;">{mrname}</span>
            </td>
            <td>{warn_badge}</td>
            <td style="text-align:right; white-space:nowrap;">{actions_html}</td>
        </tr>
        '''

    # 2. Build Ranks Table Rows
    rank_count_map = {}
    for m in members:
        lvl = m["rank_level"]
        rank_count_map[lvl] = rank_count_map.get(lvl, 0) + 1

    rank_descriptions = {
        1: "Supreme Commander of Fedrix Clan • Full Governance, Bank, Fleet, and War Command",
        2: "Executive Leadership • Member Management, Promotions, Clan Operations",
        3: "High Command Overseer • Roster Supervision, Event Coordination, Fleet Access",
        4: "Elite Combat Vanguard • Turf Battles, Heavy Weapons, Tier 4+ Fleet",
        5: "Senior Operative • Active Turf Battles, Heists, Tier 3+ Fleet",
        6: "Patrol Scout • Recon, Turf Defense, Tier 2+ Fleet Access",
        7: "Probationary Clan Recruit • Active Trial Period",
        8: "Disciplinary Action • Action & Weapon Restrictions",
        9: "Penalized Clan Rank • Demoted / Fun Clan Mascot",
        11: "Guest / Allied Clan Diplomat • Non-combatant Clan Guest"
    }

    rank_rows = ""
    for r in ranks:
        lvl = r["level"]
        cnt = rank_count_map.get(lvl, 0)
        desc = rank_descriptions.get(lvl, "Clan Member")
        perm_badge = '<span class="badge badge-green" style="font-size:11px;">CAN MANAGE</span>' if r.get("can_manage") else '<span class="badge" style="background:rgba(100,116,139,0.2); color:#94a3b8; border:1px solid #334155; font-size:11px;">MEMBER</span>'
        rank_rows += f'''
        <tr>
            <td style="width:90px;"><span style="color:#94a3b8; font-weight:700;">Level</span> <b style="color:#fff; font-size:16px;">{lvl}</b></td>
            <td style="width:160px;"><b style="color:#c084fc; font-size:15px;">{r['name']}</b></td>
            <td><span style="color:#cbd5e1; font-size:13px;">{desc}</span></td>
            <td style="width:130px;">{perm_badge}</td>
            <td style="width:110px; text-align:right;"><span class="badge badge-purple" style="font-size:12px;">{cnt} Operative{'s' if cnt != 1 else ''}</span></td>
        </tr>
        '''

    # 3. Build Vehicles Rows
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
        veh_rows += f'''
        <tr class="veh-row" data-name="{v['name'].lower()}" data-plate="{plate.lower()}">
            <td style="color:#64748b; font-weight:700;">#{v['id']}</td>
            <td><b style="color:#fff; font-size:15px;">{v['name']}</b></td>
            <td><code style="background:#0a0c12; border:1px solid #272c3d; padding:3px 8px; border-radius:4px; color:#f8fafc; font-weight:800; font-size:13px;">{plate}</code></td>
            <td><span class="badge badge-purple">{v.get('notes') or 'Rank 1+'}</span></td>
            <td>{badge}</td>
            <td style="text-align:right;">
                <button class="btn btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="renewVehicle('{v['id']}')">🛡️ +30d</button>
                <button class="btn btn-red" style="padding:4px 10px; font-size:11px; margin-left:4px;" onclick="removeVehicle('{v['id']}')">🗑️</button>
            </td>
        </tr>
        '''

    # 4. Build Events Cards
    event_cards = ""
    for e in events:
        event_cards += f'''
        <div class="card" style="border-left: 4px solid var(--purple); background:#0e1017; border-color:#1e2333;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 style="color:#c084fc; font-size:18px;">⚔️ {e['name']}</h3>
                <span class="badge badge-purple" style="font-size:12px;">{e['time_utc']} UTC</span>
            </div>
            <p style="color:var(--text-secondary); margin-top:10px; font-size:14px; line-height:1.5;">{e['description']}</p>
            <div style="margin-top:14px; display:flex; justify-content:space-between; align-items:center;">
                <span class="badge badge-green" style="font-size:11px;">+Clan Event Points</span>
                <button class="btn btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="removeEvent({e['id']})">Remove</button>
            </div>
        </div>
        '''

    # 5. Build Transactions Rows
    tx_rows = ""
    for t in txs:
        icon = '<span class="badge badge-green">DEPOSIT</span>' if t['type'] == 'deposit' else '<span class="badge badge-red">WITHDRAW</span>'
        tx_rows += f'''
        <tr>
            <td>{icon}</td>
            <td><b style="color:#fff; font-size:15px;">{format_money(t['gross_amount'])}</b></td>
            <td><span style="color:#93c5fd; font-weight:700;">{t['user_name']}</span></td>
            <td style="color:#cbd5e1;">{t['reason']}</td>
            <td style="color:#64748b; font-size:12px;">{t['created_at']}</td>
        </tr>
        '''

    # First time member dropdown options
    member_select_options = '<option value="">-- Choose your in-game character --</option>'
    for m in members:
        is_claimed = bool(m.get("discord_id"))
        suffix = f" (Claimed by @{m['discord_username']})" if is_claimed else ""
        selected = 'selected' if profile.get('libra_member_id') == m['id'] else ''
        mid = m['id']
        mname = m['name']
        mlvl = m['rank_level']
        mrname = m['rank_name']
        member_select_options += f'<option value="{mid}" {selected}>{mname} (ID {mid} • Lv {mlvl} {mrname}){suffix}</option>'
    member_select_options += '<option value="0">I am a new recruit / not on this roster</option>'

    # 6. Extract Operative Dossier Profiles for Right Vertical Panel
    def render_award_text(val):
        if not val or not str(val).strip():
            return '<span style="color:#64748b; font-style:italic; font-weight:normal;">None</span>'
        return f'<span style="color:#f59e0b; font-weight:700;">{str(val).strip()}</span>'

    libra_m = next((m for m in members if m['id'] == profile.get('libra_member_id') or m.get('discord_id') == str(user['id'])), None)
    libra_char_name = libra_m['name'] if libra_m else (profile.get('libra_member_name') or 'Operative')
    libra_char_id = str(libra_m['id']) if libra_m else (str(profile.get('libra_member_id')) if profile.get('libra_member_id') else '5392')
    libra_char_rank = f"Lv {libra_m['rank_level']} {libra_m['rank_name']}" if libra_m else profile.get('libra_rank', 'Lv 2 Co-Leader')
    libra_act = profile.get('libra_recent_activity') or 'Active clan operative'
    libra_awards = profile.get('libra_awards') or ''
    libra_awards_display = render_award_text(libra_awards)
    libra_punishments = profile.get('libra_punishments') or 'Good Standing (0 Suspensions)'
    
    if libra_m:
        libra_w_cnt = libra_m.get('warnings') or 0
        if libra_w_cnt == 0:
            libra_punishments_display = '<span style="color:#22c55e; font-weight:700;">Clean Record (0 Active Warnings)</span>'
        elif libra_w_cnt == 1:
            libra_punishments_display = '<span style="color:#fbbf24; font-weight:700;">⚠️ 1/3 Active Warning</span>'
        elif libra_w_cnt == 2:
            libra_punishments_display = '<span style="color:#f87171; font-weight:700;">⚠️ 2/3 Final Warning</span>'
        else:
            libra_punishments_display = f'<span style="color:#ef4444; font-weight:700;">🚨 {libra_w_cnt}/3 Strike Action</span>'
    else:
        libra_punishments_display = '<span style="color:#22c55e; font-weight:700;">Clean Record (0 Active Warnings)</span>'

    grand_char_name = profile.get('grand_member_name') or user['username']
    grand_char_id = profile.get('grand_member_id') or '7104'
    grand_char_rank = profile.get('grand_rank') or 'Leader / Boss (Rank 10)'
    grand_act = profile.get('grand_recent_activity') or 'Pineapple Harvest Banked • Active Fleet Operative'
    grand_awards = profile.get('grand_awards') or ''
    grand_awards_display = render_award_text(grand_awards)
    grand_punishments = profile.get('grand_punishments') or 'Clean Record (0 Active Warnings)'

    discord_name = user['username']
    discord_id = str(user['id'])
    discord_rank = profile.get('discord_rank') or ('👑 Server Founder & Command Staff' if is_admin_user(user) else 'Verified Malayali Club Operative')
    discord_act = profile.get('discord_recent_activity') or 'Authenticated via Discord OAuth2 • Command Center Active'
    discord_awards = profile.get('discord_awards') or ''
    discord_awards_display = render_award_text(discord_awards)
    discord_punishments = profile.get('discord_punishments') or 'Clean Record (0 Mutes / Warnings)'

    # Edit buttons: Visible ONLY for Rank 1, 2, and 3 in Libra (or Founder)
    grand_edit_btn = '<button class="dossier-edit-btn" onclick="openDossierModal(\'grand\')" title="Edit Grand RP Dossier">✏️ Edit</button>' if can_manage else ''
    libra_edit_btn = '<button class="dossier-edit-btn" onclick="openDossierModal(\'libra\')" title="Edit Libra RP Dossier">✏️ Edit</button>' if can_manage else ''
    discord_edit_btn = '<button class="dossier-edit-btn" onclick="openDossierModal(\'discord\')" title="Edit Discord Dossier">✏️ Edit</button>' if can_manage else ''

    total_m_count = len(members)
    online_m_count = sum(1 for m in members if m.get("is_online"))

    add_btn_html = '''
    <button class="btn btn-primary" style="padding:7px 16px; font-size:12px; margin-left:auto;" onclick="openAddMemberModal()">+ Add Member</button>
    ''' if can_manage else ''

    html = f'''
    <!DOCTYPE html>
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Libra RP (Fedrix Clan) • Thenga Network</title>
            <style>
                {COMMON_CSS}
                body {{
                    background-color: #07080c;
                    color: #f8fafc;
                    overflow-x: hidden;
                }}
                .ingame-shell {{
                    display: flex;
                    min-height: calc(100vh - 65px);
                    width: 100%;
                }}
                .ingame-sidebar {{
                    width: 280px;
                    background: #0b0d13;
                    border-right: 1px solid #1a1e2b;
                    padding: 24px 20px;
                    display: flex;
                    flex-direction: column;
                    flex-shrink: 0;
                }}
                .ingame-content {{
                    flex: 1;
                    padding: 28px 36px;
                    min-width: 0;
                    width: 100%;
                }}
                .ingame-group-title {{
                    font-size: 10px;
                    font-weight: 800;
                    letter-spacing: 1.5px;
                    text-transform: uppercase;
                    color: #475569;
                    margin: 18px 0 6px 6px;
                }}
                .ingame-nav-btn {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    padding: 10px 14px;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 700;
                    color: #94a3b8;
                    text-decoration: none;
                    cursor: pointer;
                    background: transparent;
                    border: none;
                    width: 100%;
                    text-align: left;
                    transition: all 0.15s;
                    margin-bottom: 3px;
                }}
                .ingame-nav-btn:hover {{
                    background: #151824;
                    color: #fff;
                }}
                .ingame-nav-btn.active {{
                    background: rgba(239, 68, 68, 0.14);
                    color: #fff;
                    border-left: 3px solid #ef4444;
                }}
                .ingame-side-btn {{
                    background: #141824;
                    border: 1px solid #262c3e;
                    color: #e2e8f0;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 11px;
                    border-radius: 8px;
                    text-align: center;
                    text-transform: uppercase;
                    letter-spacing: 0.8px;
                    cursor: pointer;
                    margin-top: 8px;
                    width: 100%;
                    transition: all 0.15s;
                }}
                .ingame-side-btn:hover {{
                    background: #1f2538;
                    border-color: #3b445f;
                    color: #fff;
                }}
                .ingame-btn-action {{
                    background: transparent;
                    border: 1.5px solid #ef4444;
                    color: #f87171;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 4px 10px;
                    border-radius: 4px;
                    cursor: pointer;
                    letter-spacing: 0.5px;
                    transition: all 0.15s;
                }}
                .ingame-btn-action:hover {{
                    background: #ef4444;
                    color: #fff;
                    box-shadow: 0 0 10px rgba(239,68,68,0.5);
                }}
                .ingame-btn-action.btn-kick:hover {{
                    background: #b91c1c;
                }}
                .ingame-btn-action.btn-warn {{
                    border-color: #f59e0b;
                    color: #fbbf24;
                }}
                .ingame-btn-action.btn-warn:hover {{
                    background: #f59e0b;
                    color: #000;
                    box-shadow: 0 0 10px rgba(245,158,11,0.5);
                }}
                .ingame-btn-claim {{
                    background: rgba(34, 197, 94, 0.15);
                    border: 1.5px solid #22c55e;
                    color: #4ade80;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 4px 10px;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: all 0.15s;
                }}
                .ingame-btn-claim:hover {{
                    background: #22c55e;
                    color: #fff;
                }}
                .ingame-dot {{
                    display: inline-block;
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    margin-right: 10px;
                    flex-shrink: 0;
                }}
                .dot-online {{
                    background: #22c55e;
                    box-shadow: 0 0 10px #22c55e;
                }}
                .dot-offline {{
                    background: #475569;
                }}
                .ingame-search {{
                    background: #0f121a;
                    border: 1px solid #242a3a;
                    color: #fff;
                    padding: 10px 14px;
                    border-radius: 8px;
                    font-size: 13px;
                    width: 320px;
                    margin: 0;
                }}
                .ingame-search:focus {{
                    border-color: #ef4444;
                    outline: none;
                    box-shadow: 0 0 12px rgba(239,68,68,0.35);
                }}
                .quick-stat-card {{
                    background: #0b0d14;
                    border: 1px solid #1a1e2b;
                    border-radius: 12px;
                    padding: 16px 20px;
                    cursor: pointer;
                    transition: all 0.2s;
                }}
                .quick-stat-card:hover {{
                    border-color: #ef4444;
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0,0,0,0.5);
                }}
                .modal-backdrop {{
                    display: none;
                    position: fixed;
                    top: 0; left: 0; width: 100%; height: 100%;
                    background: rgba(0, 0, 0, 0.75);
                    backdrop-filter: blur(6px);
                    z-index: 9999;
                    justify-content: center;
                    align-items: center;
                    padding: 20px;
                }}
                
                .ingame-dossier-panel {{
                    width: 380px;
                    background: #090b10;
                    border-left: 1px solid #1a1e2b;
                    padding: 22px 18px;
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                    flex-shrink: 0;
                    box-sizing: border-box;
                    margin-left: auto;
                }}
                .dossier-card {{
                    background: #0c0e15;
                    border: 1px solid #1c202d;
                    border-radius: 12px;
                    padding: 16px 18px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
                    transition: transform 0.15s, border-color 0.15s;
                    position: relative;
                }}
                .dossier-card:hover {{
                    transform: translateY(-2px);
                }}
                .card-grand {{
                    border-left: 3.5px solid #3b82f6;
                    border-color: rgba(59, 130, 246, 0.4);
                }}
                .card-libra {{
                    border-left: 3.5px solid #a855f7;
                    border-color: rgba(168, 85, 247, 0.4);
                }}
                .card-discord {{
                    border-left: 3.5px solid #5865F2;
                    border-color: rgba(88, 101, 242, 0.4);
                }}
                .dossier-label {{
                    font-size: 10px;
                    font-weight: 800;
                    color: #64748b;
                    letter-spacing: 0.8px;
                    text-transform: uppercase;
                    margin-top: 8px;
                }}
                .dossier-val {{
                    font-size: 12.5px;
                    line-height: 1.4;
                    margin-top: 2px;
                }}
                .dossier-edit-btn {{
                    background: rgba(255,255,255,0.06);
                    border: 1px solid #272c3d;
                    color: #94a3b8;
                    cursor: pointer;
                    font-size: 11px;
                    padding: 3px 7px;
                    border-radius: 5px;
                    transition: all 0.15s;
                }}
                .dossier-edit-btn:hover {{
                    color: #fff;
                    background: #272c3d;
                    border-color: #3b445f;
                }}
                @media (max-width: 1350px) {{
                    .ingame-dossier-panel {{ width: 290px; padding: 16px 12px; }}
                }}
                @media (max-width: 1100px) {{
                    .ingame-shell {{ flex-direction: column; }}
                    .ingame-sidebar, .ingame-dossier-panel {{ width: 100%; border-right: none; border-left: none; border-bottom: 1px solid #1a1e2b; }}
                    .ingame-content {{ padding: 20px; }}
                }}
                @media (max-width: 768px) {{
                    .ingame-content {{ padding: 14px 12px; }}
                    .ingame-sidebar {{ padding: 16px 14px; }}
                    .ingame-search {{ width: 100% !important; max-width: 100% !important; }}
                    .quick-stat-card {{ padding: 12px 14px; }}
                }}
            </style>
        </head>
        <body>
            {render_header(user, "Libra RP (Fedrix Clan)")}

            <div class="ingame-shell">
                <!-- IN-GAME LEFT SIDEBAR -->
                <aside class="ingame-sidebar">
                    <!-- Title & Identity -->
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 11px; font-weight: 800; color: #94a3b8; letter-spacing: 1.5px; text-transform: uppercase;">LIBRA RP</div>
                        <div style="font-size: 26px; font-weight: 900; color: #ffffff; letter-spacing: -0.5px; margin-top: 2px;">Fedrix</div>
                    </div>

                    <!-- Balance & Event Points -->
                    <div style="background: #080a0f; border: 1px solid #171b26; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px;">
                        <div style="font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 1px; text-transform: uppercase;">BALANCE</div>
                        <div style="font-size: 20px; font-weight: 900; color: #ffffff; margin-top: 2px; margin-bottom: 10px;">{format_money(bal['balance'])}</div>
                        
                        <div style="font-size: 10px; font-weight: 800; color: #64748b; letter-spacing: 1px; text-transform: uppercase;">EVENT POINTS</div>
                        <div style="font-size: 20px; font-weight: 900; color: #ffffff; margin-top: 2px;">117</div>
                    </div>

                    <!-- Navigation Items -->
                    <div class="ingame-group-title">CREW</div>
                    <button class="ingame-nav-btn active" id="btn-tab-members" onclick="switchTab('members')">
                        <span>👥 Members</span>
                        <span class="badge" style="background:rgba(239,68,68,0.18); color:#f87171; font-size:11px;">{total_m_count}/100</span>
                    </button>
                    <button class="ingame-nav-btn" id="btn-tab-ranks" onclick="switchTab('ranks')">
                        <span>🎖️ Ranks</span>
                        <span class="badge" style="background:#1e2436; color:#94a3b8; font-size:11px;">10</span>
                    </button>

                    <div class="ingame-group-title">TURF</div>
                    <button class="ingame-nav-btn" id="btn-tab-events" onclick="switchTab('events')">
                        <span>🚩 Events</span>
                        <span class="badge" style="background:#1e2436; color:#94a3b8; font-size:11px;">{len(events)}</span>
                    </button>
                    <button class="ingame-nav-btn" id="btn-tab-vehicles" onclick="switchTab('vehicles')">
                        <span>🚗 Vehicles</span>
                        <span class="badge" style="background:#1e2436; color:#94a3b8; font-size:11px;">{len(vehicles)}</span>
                    </button>

                    <div class="ingame-group-title">CLAN</div>
                    <button class="ingame-nav-btn" id="btn-tab-logs" onclick="switchTab('logs')">
                        <span>📜 Logs & Treasury</span>
                        <span class="badge badge-green" style="font-size:11px;">0% Tax</span>
                    </button>

                    <!-- Bottom Clan Actions -->
                    <div style="margin-top: auto; padding-top: 24px;">
                        <button class="ingame-side-btn" onclick="triggerRecallVehicles()">RECALL VEHICLES</button>
                        <button class="ingame-side-btn" onclick="triggerMeetingPoint()">MEETING POINT</button>
                        <button class="ingame-side-btn" style="background:rgba(88,101,242,0.15); border-color:#5865F2; color:#818cf8; margin-top:8px;" onclick="openProfileModal()">🔗 LINK IN-GAME ID</button>
                        <a href="/" class="ingame-side-btn" style="text-decoration:none; display:block; color:#ef4444; border-color:rgba(239,68,68,0.3); background:transparent; margin-top:12px;">← LEAVE TO HUB</a>
                    </div>
                </aside>

                <!-- MAIN DASHBOARD CONTENT AREA -->
                <main class="ingame-content">
                    <!-- TOP ROW: QUICK VIEWS -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 28px;">
                        <div class="quick-stat-card" onclick="switchTab('members')">
                            <div class="stat-label">Fedrix Clan Roster</div>
                            <div class="stat-val" style="color: #fff; font-size: 22px;">{total_m_count} <span style="font-size: 14px; color: #64748b;">/ 100</span></div>
                            <div style="color: #22c55e; font-size: 12px; font-weight: 700; margin-top: 4px;">● {online_m_count} Operative Online</div>
                        </div>

                        <div class="quick-stat-card" onclick="switchTab('logs')">
                            <div class="stat-label">Clan Treasury (0% Tax)</div>
                            <div class="stat-val" style="color: #22c55e; font-size: 22px;">{format_money(bal['balance'])}</div>
                            <div style="color: #94a3b8; font-size: 12px; font-weight: 600; margin-top: 4px;">Direct Fedrix Clan Bank</div>
                        </div>

                        <div class="quick-stat-card" onclick="switchTab('vehicles')">
                            <div class="stat-label">Fedrix Fleet</div>
                            <div class="stat-val" style="color: #fff; font-size: 22px;">{len(vehicles)} Cars</div>
                            <div style="color: #c084fc; font-size: 12px; font-weight: 600; margin-top: 4px;">High-tier clan fleet</div>
                        </div>

                        <div class="quick-stat-card" onclick="switchTab('events')">
                            <div class="stat-label">Daily Events & Points</div>
                            <div class="stat-val" style="color: #c084fc; font-size: 22px;">117 Pts</div>
                            <div style="color: #f59e0b; font-size: 12px; font-weight: 600; margin-top: 4px;">3 Scheduled Events</div>
                        </div>
                    </div>

                    <!-- TAB 1: MEMBERS (AUTHENTIC IN-GAME ROSTER) -->
                    <div id="view-members">
                        <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;">
                            <div>
                                <h1 style="font-size: 32px; font-weight: 900; color: #fff; letter-spacing: -0.5px;">Members</h1>
                                <div style="font-size: 18px; font-weight: 700; color: #94a3b8; margin-top: 4px;">{total_m_count}/100</div>
                            </div>
                            <div style="display: flex; gap: 12px; align-items: center;">
                                <input type="text" class="ingame-search" id="member-search" placeholder="Search by ID or name..." onkeyup="filterMembers(this.value)">
                                {add_btn_html}
                            </div>
                        </div>

                        <div class="card" style="padding: 0; overflow: hidden; background: #0a0c12; border: 1px solid #1a1e2b;">
                            <div class="table-responsive" style="margin: 0;">
                                <table style="margin: 0;">
                                    <thead>
                                        <tr style="background: #08090d; border-bottom: 1px solid #161924;">
                                            <th style="padding: 14px 18px; color: #64748b; font-size: 11px;">NAME</th>
                                            <th style="padding: 14px 18px; color: #64748b; font-size: 11px;">ID</th>
                                            <th style="padding: 14px 18px; color: #64748b; font-size: 11px;">RANK</th>
                                            <th style="padding: 14px 18px; color: #64748b; font-size: 11px;">WARNING STATUS</th>
                                            <th style="padding: 14px 18px; color: #64748b; font-size: 11px; text-align: right;">ACTIONS</th>
                                        </tr>
                                    </thead>
                                    <tbody id="members-table-body">
                                        {member_rows}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 2: RANKS HIERARCHY -->
                    <div id="view-ranks" style="display: none;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
                            <div>
                                <h1 style="font-size: 28px; font-weight: 900; color: #fff;">Clan Ranks & Hierarchy</h1>
                                <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">Fedrix Clan command structure, operational permissions, and active counts.</p>
                            </div>
                        </div>

                        <div class="card" style="padding: 0; overflow: hidden; background: #0a0c12; border: 1px solid #1a1e2b;">
                            <div class="table-responsive" style="margin: 0;">
                                <table style="margin: 0;">
                                    <thead>
                                        <tr style="background: #08090d; border-bottom: 1px solid #161924;">
                                            <th style="padding: 14px 18px;">TIER</th>
                                            <th style="padding: 14px 18px;">RANK NAME</th>
                                            <th style="padding: 14px 18px;">DUTIES & OPERATIONAL SCOPE</th>
                                            <th style="padding: 14px 18px;">GOVERNANCE</th>
                                            <th style="padding: 14px 18px; text-align: right;">OPERATIVES</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rank_rows}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 3: VEHICLES (FEDRIX FLEET) -->
                    <div id="view-vehicles" style="display: none;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;">
                            <div>
                                <h1 style="font-size: 28px; font-weight: 900; color: #fff;">Fedrix Fleet ({len(vehicles)} Cars)</h1>
                                <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">High-tier clan vehicles with rank requirements and insurance maintenance.</p>
                            </div>
                            <div style="display: flex; gap: 10px;">
                                <input type="text" class="ingame-search" id="veh-search" placeholder="Search vehicle or plate..." onkeyup="filterVehicles(this.value)">
                                <button class="btn btn-primary" onclick="openAddCarModal()">+ Add Car</button>
                            </div>
                        </div>

                        <div class="card" style="padding: 0; overflow: hidden; background: #0a0c12; border: 1px solid #1a1e2b;">
                            <div class="table-responsive" style="margin: 0;">
                                <table style="margin: 0;">
                                    <thead>
                                        <tr style="background: #08090d; border-bottom: 1px solid #161924;">
                                            <th style="padding: 14px 18px;">ID</th>
                                            <th style="padding: 14px 18px;">VEHICLE MODEL</th>
                                            <th style="padding: 14px 18px;">PLATE</th>
                                            <th style="padding: 14px 18px;">RANK REQ</th>
                                            <th style="padding: 14px 18px;">INSURANCE</th>
                                            <th style="padding: 14px 18px; text-align: right;">ACTIONS</th>
                                        </tr>
                                    </thead>
                                    <tbody id="vehicles-table-body">
                                        {veh_rows}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 4: EVENTS RADAR -->
                    <div id="view-events" style="display: none;">
                        <div style="margin-bottom: 20px;">
                            <h1 style="font-size: 28px; font-weight: 900; color: #fff;">Events Radar (3 Scheduled)</h1>
                            <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">Live clan turf and combat events for Libra RP Fedrix Clan.</p>
                        </div>
                        <div class="grid-2">{event_cards}</div>
                    </div>

                    <!-- TAB 5: LOGS & TREASURY -->
                    <div id="view-logs" style="display: none;">
                        <div style="margin-bottom: 20px;">
                            <h1 style="font-size: 28px; font-weight: 900; color: #fff;">Clan Treasury & Transaction Logs</h1>
                            <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">Fedrix Clan Bank features 0% Tax on both deposits and withdrawals.</p>
                        </div>

                        <div class="grid-3" style="margin-bottom: 24px;">
                            <div class="card" style="background:#0a0c12; border: 1px solid #1a1e2b;">
                                <div class="stat-label">Treasury Balance</div>
                                <div class="stat-val" style="color:#22c55e;">{format_money(bal['balance'])}</div>
                            </div>
                            <div class="card" style="background:#0a0c12; border: 1px solid #1a1e2b;">
                                <div class="stat-label">Total Deposited</div>
                                <div class="stat-val" style="color:#10b981;">{format_money(bal['total_deposited'])}</div>
                            </div>
                            <div class="card" style="background:#0a0c12; border: 1px solid #1a1e2b;">
                                <div class="stat-label">Total Withdrawn</div>
                                <div class="stat-val" style="color:#ef4444;">{format_money(bal['total_withdrawn'])}</div>
                            </div>
                        </div>

                        <div class="grid-2" style="margin-bottom: 28px;">
                            <div class="card" style="background:#0a0c12; border: 1px solid #1a1e2b;">
                                <h3 style="color:#10b981; margin-bottom:12px;">📥 Deposit to Libra Fund (0% Tax)</h3>
                                <label style="font-size:11px; font-weight:800; color:#94a3b8;">Amount:</label>
                                <input id="dep-amt" type="text" placeholder="250k or 1M">
                                <label style="font-size:11px; font-weight:800; color:#94a3b8;">Reason:</label>
                                <input id="dep-reason" type="text" placeholder="Event bonus, Car sale, Clan task">
                                <button class="btn btn-green" style="width:100%;" onclick="submitDeposit('librarp')">Confirm Deposit</button>
                            </div>

                            <div class="card" style="background:#0a0c12; border: 1px solid #1a1e2b;">
                                <h3 style="color:#ef4444; margin-bottom:12px;">📤 Withdraw from Libra Fund (0% Tax)</h3>
                                <label style="font-size:11px; font-weight:800; color:#94a3b8;">Amount:</label>
                                <input id="with-amt" type="text" placeholder="500k">
                                <label style="font-size:11px; font-weight:800; color:#94a3b8;">Reason:</label>
                                <input id="with-reason" type="text" placeholder="Weapons, Clan car purchase">
                                <button class="btn btn-red" style="width:100%;" onclick="submitWithdraw('librarp')">Confirm Withdrawal</button>
                            </div>
                        </div>

                        <div class="card" style="padding: 0; overflow: hidden; background: #0a0c12; border: 1px solid #1a1e2b;">
                            <div style="padding: 16px 20px; border-bottom: 1px solid #161924;">
                                <h3 style="color:#fff; font-size:16px;">📜 Recent Clan Transactions</h3>
                            </div>
                            <div class="table-responsive" style="margin: 0;">
                                <table style="margin:0;">
                                    <thead>
                                        <tr style="background: #08090d;">
                                            <th>TYPE</th><th>AMOUNT</th><th>MEMBER</th><th>REASON</th><th>DATE</th>
                                        </tr>
                                    </thead>
                                    <tbody>{tx_rows}</tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </main>

                <!-- RIGHT VERTICAL PANEL: 3 IN-GAME & DISCORD DOSSIER DIVISIONS -->
                <aside class="ingame-dossier-panel">
                    <!-- DIVISION 1: GRAND RP (EN2) -->
                    <div class="dossier-card card-grand">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; align-items: center; gap: 7px;">
                                <span style="font-size: 16px;">🌆</span>
                                <span style="color: #60a5fa; font-weight: 900; font-size: 12px; letter-spacing: 0.8px; text-transform: uppercase;">GRAND RP (EN2)</span>
                            </div>
                            {grand_edit_btn}
                        </div>
                        <div style="font-size: 16px; font-weight: 800; color: #fff; margin-top: 8px;">
                            {grand_char_name} <span style="font-size: 12px; color: #64748b; font-weight: 700;">#{grand_char_id}</span>
                        </div>
                        <div style="font-size: 13px; font-weight: 700; color: #93c5fd; margin-top: 2px; margin-bottom: 8px;">
                            {grand_char_rank}
                        </div>

                        <div class="dossier-label">RECENT ACTIVITY</div>
                        <div class="dossier-val" style="color: #cbd5e1;">{grand_act}</div>

                        <div class="dossier-label">MEDALS & AWARDS (BY LEADER)</div>
                        <div class="dossier-val">{grand_awards_display}</div>

                        <div class="dossier-label">DISCIPLINARY RECORD</div>
                        <div class="dossier-val" style="color: #22c55e; font-weight: 700;">{grand_punishments}</div>
                    </div>

                    <!-- DIVISION 2: LIBRA RP (FEDRIX) -->
                    <div class="dossier-card card-libra">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; align-items: center; gap: 7px;">
                                <span style="font-size: 16px;">⚖️</span>
                                <span style="color: #c084fc; font-weight: 900; font-size: 12px; letter-spacing: 0.8px; text-transform: uppercase;">LIBRA RP (FEDRIX)</span>
                            </div>
                            {libra_edit_btn}
                        </div>
                        <div style="font-size: 16px; font-weight: 800; color: #fff; margin-top: 8px;">
                            {libra_char_name} <span style="font-size: 12px; color: #64748b; font-weight: 700;">ID #{libra_char_id}</span>
                        </div>
                        <div style="font-size: 13px; font-weight: 700; color: #d8b4fe; margin-top: 2px; margin-bottom: 8px;">
                            {libra_char_rank}
                        </div>

                        <div class="dossier-label">RECENT ACTIVITY</div>
                        <div class="dossier-val" style="color: #cbd5e1;">{libra_act}</div>

                        <div class="dossier-label">MEDALS & AWARDS (BY LEADER)</div>
                        <div class="dossier-val">{libra_awards_display}</div>

                        <div class="dossier-label">DISCIPLINARY RECORD</div>
                        <div class="dossier-val">{libra_punishments_display}</div>
                    </div>

                    <!-- DIVISION 3: DISCORD DOSSIER -->
                    <div class="dossier-card card-discord">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; align-items: center; gap: 7px;">
                                <span style="font-size: 16px;">🎮</span>
                                <span style="color: #818cf8; font-weight: 900; font-size: 12px; letter-spacing: 0.8px; text-transform: uppercase;">DISCORD DOSSIER</span>
                            </div>
                            {discord_edit_btn}
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; margin-top: 8px;">
                            <img src="{user['avatar_url']}" style="width: 26px; height: 26px; border-radius: 50%; border: 1.5px solid #5865F2;">
                            <div>
                                <span style="font-size: 15px; font-weight: 800; color: #fff;">{discord_name}</span>
                                <span style="font-size: 11px; color: #64748b; margin-left: 4px;">#{discord_id[-4:]}</span>
                            </div>
                        </div>
                        <div style="font-size: 13px; font-weight: 700; color: #818cf8; margin-top: 2px; margin-bottom: 8px;">
                            {discord_rank}
                        </div>

                        <div class="dossier-label">RECENT ACTIVITY</div>
                        <div class="dossier-val" style="color: #cbd5e1;">{discord_act}</div>

                        <div class="dossier-label">SERVER RECOGNITIONS</div>
                        <div class="dossier-val">{discord_awards_display}</div>

                        <div class="dossier-label">DISCIPLINARY RECORD</div>
                        <div class="dossier-val" style="color: #22c55e; font-weight: 700;">{discord_punishments}</div>
                    </div>
                </aside>
            </div>

            <!-- MODAL 1: EDIT RANK -->
            <div id="rankModal" class="modal-backdrop">
                <div class="card" style="max-width: 440px; width: 100%; border: 1.5px solid #ef4444; box-shadow: 0 10px 40px rgba(0,0,0,0.8);">
                    <h3 style="color: #fff; font-size: 18px; font-weight: 900; margin-bottom: 4px;">🎖️ Edit Clan Member Rank</h3>
                    <p id="rank-modal-sub" style="color: #94a3b8; font-size: 13px; margin-bottom: 16px;">Update rank for member</p>
                    <input type="hidden" id="edit-member-id">
                    
                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase;">Select New Rank:</label>
                    <select id="new-rank-select" style="margin-top: 6px; margin-bottom: 20px;">
                        <option value="1|Leader">Level 1 - Leader (Supreme Commander)</option>
                        <option value="2|Co-Leader">Level 2 - Co-Leader (Executive Command)</option>
                        <option value="3|Supervisor">Level 3 - Supervisor (High Command)</option>
                        <option value="4|Enforcer">Level 4 - Enforcer (Combat Vanguard)</option>
                        <option value="5|Pro">Level 5 - Pro (Senior Operative)</option>
                        <option value="6|Ranger">Level 6 - Ranger (Patrol Scout)</option>
                        <option value="7|Trainee">Level 7 - Trainee (Recruit)</option>
                        <option value="8|SUSPENDED">Level 8 - SUSPENDED (Action Restriction)</option>
                        <option value="9|VAAZHA">Level 9 - VAAZHA (Demoted / Fun Rank)</option>
                        <option value="11|GUEST">Level 11 - GUEST (Allied Clan Visitor)</option>
                    </select>

                    <div style="display: flex; gap: 10px;">
                        <button class="btn btn-primary" style="flex: 1;" onclick="submitRankChange()">Update Rank</button>
                        <button class="btn btn-secondary" onclick="closeModal('rankModal')">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- MODAL 2: KICK CONFIRMATION -->
            <div id="kickModal" class="modal-backdrop">
                <div class="card" style="max-width: 420px; width: 100%; border: 1.5px solid #ef4444; box-shadow: 0 10px 40px rgba(0,0,0,0.8);">
                    <h3 style="color: #ef4444; font-size: 18px; font-weight: 900; margin-bottom: 6px;">⚠️ Kick Clan Member?</h3>
                    <p id="kick-modal-sub" style="color: #cbd5e1; font-size: 14px; margin-bottom: 20px; line-height: 1.5;">Are you sure you want to remove this operative from the Fedrix Clan roster?</p>
                    <input type="hidden" id="kick-member-id">

                    <div style="display: flex; gap: 10px;">
                        <button class="btn btn-red" style="flex: 1;" onclick="submitKick()">Confirm Kick</button>
                        <button class="btn btn-secondary" onclick="closeModal('kickModal')">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- MODAL: LIBRA RP DISCIPLINARY / WARNINGS -->
            <div id="warnModal" class="modal-backdrop">
                <div class="card" style="max-width: 490px; width: 100%; border: 1.5px solid #f59e0b; box-shadow: 0 16px 50px rgba(0,0,0,0.85); border-radius: 14px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
                        <h3 style="color: #fbbf24; font-size: 18px; font-weight: 900; margin: 0;">⚠️ Libra RP Disciplinary Action</h3>
                        <span id="warn-strike-badge" class="badge badge-green">0/3 CLEAN</span>
                    </div>
                    <p id="warn-modal-sub" style="color: #cbd5e1; font-size: 13px; margin-bottom: 14px;">Managing clan strikes for operative</p>
                    <input type="hidden" id="warn-member-id">

                    <!-- Warning History Box -->
                    <div style="margin-bottom: 16px;">
                        <div style="font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase; margin-bottom: 6px;">Active Warning History (Isolated to Libra):</div>
                        <div id="warn-history-box" style="max-height: 150px; overflow-y: auto; background: #080a10; border: 1px solid #1a1e2b; border-radius: 8px; padding: 12px; font-size: 12px; color: #94a3b8;">
                            Loading history...
                        </div>
                    </div>

                    <!-- Issue Warning Form (Leader / Co-Leader / Supervisor) -->
                    <div id="warn-action-box" style="display: {'block' if can_manage else 'none'}; background: #0c0e15; border: 1px solid #272c3d; border-radius: 8px; padding: 14px; margin-bottom: 16px;">
                        <label style="font-size: 11px; font-weight: 800; color: #f59e0b; text-transform: uppercase;">Issue Disciplinary Strike (Reason):</label>
                        <input id="warn-reason-input" type="text" placeholder="e.g. Broke turf rule, insubordination, event absence" style="margin-top: 6px; margin-bottom: 12px;">
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-red" style="flex: 1; padding: 9px; font-size: 12px;" onclick="submitIssueWarning()">⚠️ Issue Warning (+1 Strike)</button>
                            <button class="btn btn-secondary" style="padding: 9px 12px; font-size: 12px;" onclick="submitClearWarnings()">🔄 Reset to 0</button>
                        </div>
                    </div>

                    <div style="display: flex; justify-content: flex-end;">
                        <button class="btn btn-secondary" style="padding: 8px 18px;" onclick="closeModal('warnModal')">Close</button>
                    </div>
                </div>
            </div>

            <!-- MODAL 3: ADD MEMBER -->
            <div id="addMemberModal" class="modal-backdrop">
                <div class="card" style="max-width: 440px; width: 100%; border: 1.5px solid #ef4444; box-shadow: 0 10px 40px rgba(0,0,0,0.8);">
                    <h3 style="color: #fff; font-size: 18px; font-weight: 900; margin-bottom: 4px;">➕ Add Clan Member to Fedrix</h3>
                    <p style="color: #94a3b8; font-size: 13px; margin-bottom: 16px;">Enroll a new operative into the clan database</p>
                    
                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">In-Game ID (e.g. 5890):</label>
                    <input id="add-member-id" type="number" placeholder="5890">

                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Character Name:</label>
                    <input id="add-member-name" type="text" placeholder="e.g. Dexter Morgan">

                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Initial Rank:</label>
                    <select id="add-member-rank" style="margin-bottom: 20px;">
                        <option value="7|Trainee">Level 7 - Trainee (Recruit)</option>
                        <option value="6|Ranger">Level 6 - Ranger</option>
                        <option value="5|Pro">Level 5 - Pro</option>
                        <option value="4|Enforcer">Level 4 - Enforcer</option>
                        <option value="3|Supervisor">Level 3 - Supervisor</option>
                        <option value="11|GUEST">Level 11 - GUEST</option>
                    </select>

                    <div style="display: flex; gap: 10px;">
                        <button class="btn btn-primary" style="flex: 1;" onclick="submitAddMember()">Add Member</button>
                        <button class="btn btn-secondary" onclick="closeModal('addMemberModal')">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- MODAL 4: ADD VEHICLE -->
            <div id="addCarModal" class="modal-backdrop">
                <div class="card" style="max-width: 440px; width: 100%; border: 1.5px solid #a855f7;">
                    <h3 style="color: #c084fc; font-size: 18px; font-weight: 900; margin-bottom: 16px;">🏎️ Add Car to Fedrix Fleet</h3>
                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Vehicle Model:</label>
                    <input id="new-veh-name" type="text" placeholder="e.g. Pegassi Terzo">
                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">License Plate:</label>
                    <input id="new-veh-plate" type="text" placeholder="e.g. FEDRIX25">
                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Min Rank Required (1-10):</label>
                    <input id="new-veh-rank" type="text" placeholder="4">

                    <div style="display: flex; gap: 10px; margin-top: 10px;">
                        <button class="btn btn-purple" style="flex: 1;" onclick="submitAddCar()">Add Vehicle</button>
                        <button class="btn btn-secondary" onclick="closeModal('addCarModal')">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- MODAL 5: FIRST-TIME PROFILE SETUP & LINKING -->
            <div id="profileModal" class="modal-backdrop" style="{"display: flex;" if is_first_time else "display: none;"}">
                <div class="card" style="max-width: 500px; width: 100%; border: 1.5px solid var(--accent); box-shadow: 0 16px 50px rgba(0,0,0,0.85); border-radius: 16px;">
                    <div style="text-align: center; margin-bottom: 18px;">
                        <img src="/logo.png" style="width: 64px; height: auto; filter: drop-shadow(0 4px 12px rgba(239,68,68,0.5));">
                        <h2 style="color: #fff; font-size: 20px; font-weight: 900; margin-top: 10px; text-transform: uppercase;">
                            Connect Your In-Game Operatives
                        </h2>
                        <p style="color: #94a3b8; font-size: 13px; margin-top: 4px;">
                            Link your Discord account to your Grand RP & Libra RP characters
                        </p>
                    </div>

                    <!-- Libra RP Select -->
                    <div style="background: #090a0f; border: 1px solid #1a1e2b; border-left: 3px solid #a855f7; border-radius: 8px; padding: 12px; margin-bottom: 14px;">
                        <label style="font-size: 11px; font-weight: 800; color: #c084fc; text-transform: uppercase;">⚖️ Libra RP (Fedrix Clan Character):</label>
                        <select id="link-libra-id" style="margin-top: 6px; margin-bottom: 4px;">
                            {member_select_options}
                        </select>
                        <span style="font-size: 11px; color: #64748b;">Select your in-game clan identity from the 28 seeded members</span>
                    </div>

                    <!-- Grand RP Input -->
                    <div style="background: #090a0f; border: 1px solid #1a1e2b; border-left: 3px solid #3b82f6; border-radius: 8px; padding: 12px; margin-bottom: 20px;">
                        <label style="font-size: 11px; font-weight: 800; color: #60a5fa; text-transform: uppercase;">🌆 Grand RP (EN2 Character):</label>
                        <input id="link-grand-name" type="text" value="{profile.get('grand_member_name') or user['username']}" placeholder="Character Name (e.g. Haris Thenga)" style="margin-top: 6px; margin-bottom: 8px;">
                        
                        <label style="font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase;">Grand RP Rank:</label>
                        <select id="link-grand-rank" style="margin-top: 4px; margin-bottom: 4px;">
                            <option value="Family Member (Rank 1)">Family Member (Rank 1)</option>
                            <option value="Enforcer (Rank 3)">Enforcer (Rank 3)</option>
                            <option value="High Command (Rank 7)">High Command (Rank 7)</option>
                            <option value="Co-Leader (Rank 9)">Co-Leader (Rank 9)</option>
                            <option value="Leader / Boss (Rank 10)">Leader / Boss (Rank 10)</option>
                        </select>
                    </div>

                    <div style="display: flex; gap: 10px;">
                        <button id="btn-save-personas-libra" class="btn btn-primary" style="flex: 1; padding: 12px;" onclick="submitLinkProfiles(this)">Save & Link Personas</button>
                        <button class="btn btn-secondary" onclick="dismissProfileModal()">Later</button>
                    </div>
                </div>
            </div>

                        <!-- MODAL 6: EDIT DOSSIER -->
            <div id="dossierModal" class="modal-backdrop">
                <div class="card" style="max-width: 480px; width: 100%; border: 1.5px solid var(--accent); box-shadow: 0 16px 50px rgba(0,0,0,0.85); border-radius: 14px;">
                    <h3 id="dossier-modal-title" style="color: #fff; font-size: 18px; font-weight: 900; margin-bottom: 4px;">✏️ Edit Operative Dossier</h3>
                    <p style="color: #94a3b8; font-size: 13px; margin-bottom: 16px;">Update activity, awards, and disciplinary details</p>
                    <input type="hidden" id="dossier-type">

                    <div id="dossier-field-name-box">
                        <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Character / Operative Name:</label>
                        <input id="dossier-input-name" type="text">
                    </div>

                    <div id="dossier-field-id-box">
                        <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">In-Game ID / Number:</label>
                        <input id="dossier-input-id" type="text">
                    </div>

                    <div id="dossier-field-rank-box">
                        <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Rank / Title:</label>
                        <input id="dossier-input-rank" type="text">
                    </div>

                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Recent Activity:</label>
                    <input id="dossier-input-activity" type="text">

                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Medals & Awards (By Leader):</label>
                    <input id="dossier-input-awards" type="text">

                    <label style="font-size: 11px; font-weight: 800; color: #94a3b8;">Disciplinary Record / Punishments:</label>
                    <input id="dossier-input-punishments" type="text">

                    <div style="display: flex; gap: 10px; margin-top: 10px;">
                        <button class="btn btn-primary" style="flex: 1;" onclick="submitDossierEdit()">Save Changes</button>
                        <button class="btn btn-secondary" onclick="closeModal('dossierModal')">Cancel</button>
                    </div>
                </div>
            </div>

            <!-- TOAST BANNER -->
            <div id="toast-banner" style="display:none; position:fixed; bottom:24px; right:24px; background:#10131d; border:1.5px solid #22c55e; color:#fff; padding:14px 20px; border-radius:10px; box-shadow:0 10px 30px rgba(0,0,0,0.8); z-index:99999; font-weight:700; font-size:14px;"></div>

            <script>
                                function openDossierModal(type) {{
                    document.getElementById('dossier-type').value = type;
                    let title = document.getElementById('dossier-modal-title');
                    if (type === 'grand') {{
                        title.innerText = '🌆 Edit Grand RP (EN2) Dossier';
                        document.getElementById('dossier-input-name').value = "{grand_char_name}";
                        document.getElementById('dossier-input-id').value = "{grand_char_id}";
                        document.getElementById('dossier-input-rank').value = "{grand_char_rank}";
                        document.getElementById('dossier-input-activity').value = "{grand_act}";
                        document.getElementById('dossier-input-awards').value = "{grand_awards}";
                        document.getElementById('dossier-input-punishments').value = "{grand_punishments}";
                    }} else if (type === 'libra') {{
                        title.innerText = '⚖️ Edit Libra RP (Fedrix) Dossier';
                        document.getElementById('dossier-input-name').value = "{libra_char_name}";
                        document.getElementById('dossier-input-id').value = "{libra_char_id}";
                        document.getElementById('dossier-input-rank').value = "{libra_char_rank}";
                        document.getElementById('dossier-input-activity').value = "{libra_act}";
                        document.getElementById('dossier-input-awards').value = "{libra_awards}";
                        document.getElementById('dossier-input-punishments').value = "{libra_punishments}";
                    }} else if (type === 'discord') {{
                        title.innerText = '🎮 Edit Discord Operative Dossier';
                        document.getElementById('dossier-input-name').value = "{discord_name}";
                        document.getElementById('dossier-input-id').value = "{discord_id}";
                        document.getElementById('dossier-input-rank').value = "{discord_rank}";
                        document.getElementById('dossier-input-activity').value = "{discord_act}";
                        document.getElementById('dossier-input-awards').value = "{discord_awards}";
                        document.getElementById('dossier-input-punishments').value = "{discord_punishments}";
                    }}
                    openModal('dossierModal');
                }}

                async function submitDossierEdit() {{
                    let type = document.getElementById('dossier-type').value;
                    let payload = {{}};
                    let name = document.getElementById('dossier-input-name').value;
                    let id = document.getElementById('dossier-input-id').value;
                    let rank = document.getElementById('dossier-input-rank').value;
                    let act = document.getElementById('dossier-input-activity').value;
                    let awards = document.getElementById('dossier-input-awards').value;
                    let punishments = document.getElementById('dossier-input-punishments').value;

                    if (type === 'grand') {{
                        payload = {{
                            grand_member_name: name,
                            grand_member_id: id,
                            grand_rank: rank,
                            grand_recent_activity: act,
                            grand_awards: awards,
                            grand_punishments: punishments
                        }};
                    }} else if (type === 'libra') {{
                        payload = {{
                            libra_recent_activity: act,
                            libra_awards: awards,
                            libra_punishments: punishments
                        }};
                    }} else if (type === 'discord') {{
                        payload = {{
                            discord_rank: rank,
                            discord_recent_activity: act,
                            discord_awards: awards,
                            discord_punishments: punishments
                        }};
                    }}

                    let res = await fetch('/api/user/dossier', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(payload)
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("Dossier updated successfully!");
                        setTimeout(() => location.reload(), 600);
                    }} else {{
                        alert("Error: " + d.error);
                    }}
                }}

                function switchTab(tab) {{
                    document.getElementById('view-members').style.display = tab === 'members' ? 'block' : 'none';
                    document.getElementById('view-ranks').style.display = tab === 'ranks' ? 'block' : 'none';
                    document.getElementById('view-vehicles').style.display = tab === 'vehicles' ? 'block' : 'none';
                    document.getElementById('view-events').style.display = tab === 'events' ? 'block' : 'none';
                    document.getElementById('view-logs').style.display = tab === 'logs' ? 'block' : 'none';

                    document.querySelectorAll('.ingame-nav-btn').forEach(b => b.classList.remove('active'));
                    let activeBtn = document.getElementById('btn-tab-' + tab);
                    if (activeBtn) activeBtn.classList.add('active');
                }}

                function filterMembers(q) {{
                    q = q.toLowerCase().trim();
                    document.querySelectorAll('#members-table-body tr').forEach(r => {{
                        let name = r.getAttribute('data-name') || '';
                        let id = r.getAttribute('data-id') || '';
                        if (name.includes(q) || id.includes(q)) {{
                            r.style.display = '';
                        }} else {{
                            r.style.display = 'none';
                        }}
                    }});
                }}

                function filterVehicles(q) {{
                    q = q.toLowerCase().trim();
                    document.querySelectorAll('#vehicles-table-body tr').forEach(r => {{
                        let name = r.getAttribute('data-name') || '';
                        let plate = r.getAttribute('data-plate') || '';
                        if (name.includes(q) || plate.includes(q)) {{
                            r.style.display = '';
                        }} else {{
                            r.style.display = 'none';
                        }}
                    }});
                }}

                function showToast(msg, isSuccess = true) {{
                    let t = document.getElementById('toast-banner');
                    t.style.borderColor = isSuccess ? '#22c55e' : '#ef4444';
                    t.innerHTML = msg;
                    t.style.display = 'block';
                    setTimeout(() => {{ t.style.display = 'none'; }}, 4500);
                }}

                // Instant suppression if modal was already dismissed or saved
                if (localStorage.getItem('thenga_profile_dismissed') === 'true') {{
                    var pm = document.getElementById('profileModal');
                    if (pm) pm.style.display = 'none';
                }}

                function dismissProfileModal() {{
                    localStorage.setItem('thenga_profile_dismissed', 'true');
                    closeModal('profileModal');
                    fetch('/api/user/dismiss_profile_prompt', {{ method: 'POST' }}).catch(() => {{}});
                }}

                function closeModal(id) {{
                    document.getElementById(id).style.display = 'none';
                }}

                function openModal(id) {{
                    document.getElementById(id).style.display = 'flex';
                }}

                function openProfileModal() {{
                    openModal('profileModal');
                }}

                function openRankModal(id, name, level, rankName) {{
                    document.getElementById('edit-member-id').value = id;
                    document.getElementById('rank-modal-sub').innerText = 'Updating rank for ' + name + ' (ID ' + id + ')';
                    let select = document.getElementById('new-rank-select');
                    let targetVal = level + '|' + rankName;
                    for (let i = 0; i < select.options.length; i++) {{
                        if (select.options[i].value.startsWith(level + '|')) {{
                            select.selectedIndex = i;
                            break;
                        }}
                    }}
                    openModal('rankModal');
                }}

                async function submitRankChange() {{
                    let memberId = document.getElementById('edit-member-id').value;
                    let val = document.getElementById('new-rank-select').value;
                    let parts = val.split('|');
                    let newLevel = parseInt(parts[0]);
                    let newRank = parts[1];

                    let res = await fetch('/api/libra/member/rank', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ member_id: memberId, new_level: newLevel, new_rank: newRank }})
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("Rank updated successfully for operative!");
                        setTimeout(() => location.reload(), 800);
                    }} else {{
                        alert("Error: " + d.error);
                    }}
                }}

                function openKickModal(id, name, level) {{
                    document.getElementById('kick-member-id').value = id;
                    document.getElementById('kick-modal-sub').innerText = 'Are you sure you want to kick ' + name + ' (ID ' + id + ', Lv ' + level + ') from Fedrix Clan?';
                    openModal('kickModal');
                }}

                async function submitKick() {{
                    let memberId = document.getElementById('kick-member-id').value;
                    let res = await fetch('/api/libra/member/kick', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ member_id: memberId }})
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("Operative removed from clan roster.");
                        setTimeout(() => location.reload(), 800);
                    }} else {{
                        alert("Error: " + d.error);
                    }}
                }}

                async function openWarnModal(id, name, curStrikes) {{
                    document.getElementById('warn-member-id').value = id;
                    document.getElementById('warn-modal-sub').innerText = 'Managing clan warnings for ' + name + ' (ID ' + id + ')';
                    let badge = document.getElementById('warn-strike-badge');
                    if (curStrikes === 0) {{
                        badge.className = 'badge badge-green';
                        badge.style = '';
                        badge.innerText = '0/3 CLEAN';
                    }} else if (curStrikes === 1) {{
                        badge.className = 'badge';
                        badge.style = 'background:rgba(245,158,11,0.2); color:#fbbf24; border:1px solid #f59e0b;';
                        badge.innerText = '1/3 WARN';
                    }} else if (curStrikes === 2) {{
                        badge.className = 'badge';
                        badge.style = 'background:rgba(239,68,68,0.2); color:#f87171; border:1px solid #ef4444;';
                        badge.innerText = '2/3 FINAL';
                    }} else {{
                        badge.className = 'badge badge-red';
                        badge.style = '';
                        badge.innerText = curStrikes + '/3 STRIKE';
                    }}
                    
                    let histBox = document.getElementById('warn-history-box');
                    histBox.innerHTML = '<span style="color:#64748b;">Loading warning history...</span>';
                    
                    try {{
                        let res = await fetch('/api/libra/member/warnings?member_id=' + id);
                        let d = await res.json();
                        if (d.success && d.warnings && d.warnings.length > 0) {{
                            let hHtml = '<div style="display:flex; flex-direction:column; gap:8px;">';
                            d.warnings.forEach(w => {{
                                let dateStr = (w.created_at || '').substring(0, 16);
                                hHtml += '<div style="background:#0e111a; border:1px solid #232838; padding:8px 10px; border-radius:6px;">' +
                                         '<div style="display:flex; justify-content:space-between; align-items:center;">' +
                                         '<span style="color:#fbbf24; font-weight:800; font-size:11px;">⚠️ Strike #' + w.strike_number + '</span>' +
                                         '<span style="color:#64748b; font-size:10px;">' + dateStr + '</span>' +
                                         '</div>' +
                                         '<div style="color:#f8fafc; font-size:12px; margin-top:3px;">' + w.reason + '</div>' +
                                         '<div style="color:#64748b; font-size:10px; margin-top:3px;">Issued by: <b style="color:#cbd5e1;">' + w.issued_by + '</b></div>' +
                                         '</div>';
                            }});
                            hHtml += '</div>';
                            histBox.innerHTML = hHtml;
                        }} else {{
                            histBox.innerHTML = '<span style="color:#22c55e; font-weight:700;">✓ Clean record. No active strikes on record for this operative.</span>';
                        }}
                    }} catch (e) {{
                        histBox.innerHTML = '<span style="color:#ef4444;">Failed to load warning history.</span>';
                    }}
                    
                    let reasonInp = document.getElementById('warn-reason-input');
                    if (reasonInp) reasonInp.value = '';
                    openModal('warnModal');
                }}

                async function submitIssueWarning() {{
                    let memberId = document.getElementById('warn-member-id').value;
                    let reasonInp = document.getElementById('warn-reason-input');
                    let reason = reasonInp ? reasonInp.value.trim() : '';
                    if (!reason) {{
                        alert("Please enter a reason for the warning.");
                        return;
                    }}
                    let res = await fetch('/api/libra/member/warn', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ member_id: memberId, reason: reason }})
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("⚠️ Warning strike issued to operative!");
                        setTimeout(() => location.reload(), 700);
                    }} else {{
                        alert("Error: " + (d.error || "Failed to issue warning"));
                    }}
                }}

                async function submitClearWarnings() {{
                    let memberId = document.getElementById('warn-member-id').value;
                    if (!confirm("Are you sure you want to clear all active strikes for this member and reset to clean standing?")) return;
                    let res = await fetch('/api/libra/member/clear_warn', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ member_id: memberId }})
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("✓ All warnings cleared for operative!");
                        setTimeout(() => location.reload(), 700);
                    }} else {{
                        alert("Error: " + (d.error || "Failed to clear warnings"));
                    }}
                }}

                function openAddMemberModal() {{
                    openModal('addMemberModal');
                }}

                async function submitAddMember() {{
                    let id = document.getElementById('add-member-id').value;
                    let name = document.getElementById('add-member-name').value;
                    let val = document.getElementById('add-member-rank').value;
                    let parts = val.split('|');
                    let rankLevel = parseInt(parts[0]);
                    let rankName = parts[1];

                    if (!id || !name) return alert("Please fill in ID and character name");

                    let res = await fetch('/api/libra/member/add', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ id, name, rank_level: rankLevel, rank_name: rankName }})
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("New operative enrolled!");
                        setTimeout(() => location.reload(), 800);
                    }} else {{
                        alert("Error: " + d.error);
                    }}
                }}

                async function claimLibraProfile(id, name) {{
                    if (!confirm("Claim " + name + " (ID " + id + ") as your in-game identity?")) return;
                    let res = await fetch('/api/libra/link_profile', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ member_id: id }})
                    }});
                    let d = await res.json();
                    if (d.success) {{
                        showToast("Profile linked to your Discord account!");
                        setTimeout(() => location.reload(), 800);
                    }} else {{
                        alert("Error: " + d.error);
                    }}
                }}

                async function submitLinkProfiles(btn) {{
                    let targetBtn = btn || document.getElementById('btn-save-personas-libra');
                    let oldText = targetBtn ? targetBtn.innerText : "Save & Link Personas";
                    if (targetBtn) {{
                        targetBtn.innerText = "⏳ Saving...";
                        targetBtn.disabled = true;
                    }}

                    try {{
                        let libraEl = document.getElementById('link-libra-id');
                        let grandEl = document.getElementById('link-grand-name');
                        let rankEl = document.getElementById('link-grand-rank');

                        let libraId = libraEl ? libraEl.value : '';
                        let grandName = grandEl ? grandEl.value : '';
                        let grandRank = rankEl ? rankEl.value : '';

                        let res = await fetch('/api/user/link_profiles', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{ libra_member_id: libraId, grand_name: grandName, grand_rank: grandRank }})
                        }});
                        let d = await res.json();
                        if (d.success) {{
                            localStorage.setItem('thenga_profile_dismissed', 'true');
                            if (targetBtn) targetBtn.innerText = "✓ Linked!";
                            showToast("In-game personas linked!");
                            setTimeout(() => location.reload(), 600);
                        }} else {{
                            alert("Error: " + (d.error || "Failed to link personas"));
                            if (targetBtn) {{
                                targetBtn.innerText = oldText;
                                targetBtn.disabled = false;
                            }}
                        }}
                    }} catch (err) {{
                        alert("Network or server error: " + err);
                        if (targetBtn) {{
                            targetBtn.innerText = oldText;
                            targetBtn.disabled = false;
                        }}
                    }}
                }}

                function triggerRecallVehicles() {{
                    showToast("🚗 RECALL BROADCAST: All 24 Fedrix clan vehicles have been recalled to Clan HQ garage!");
                }}

                function triggerMeetingPoint() {{
                    showToast("📍 GPS BROADCAST: Clan meeting point marked at Fedrix Compound (Coords: 412.5, -980.2).");
                }}

                function openAddCarModal() {{
                    openModal('addCarModal');
                }}

                async function submitAddCar() {{
                    let name = document.getElementById('new-veh-name').value;
                    let plate = document.getElementById('new-veh-plate').value;
                    let rank = document.getElementById('new-veh-rank').value || "1";
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
    '''
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

    image_url = data.get("image_url")
    exp = datetime.now(timezone.utc) + timedelta(days=days) if days > 0 else None
    db.add_vehicle(server, name, plate, exp, notes, user["username"], image_url)
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

async def api_libra_member_rank(request: web.Request):
    user = require_user(request)
    data = await request.json()
    member_id = int(data.get("member_id", 0))
    new_level = int(data.get("new_level", 0))
    new_rank = str(data.get("new_rank", "")).strip()

    if not member_id or not new_level or not new_rank:
        return web.json_response({"success": False, "error": "Invalid parameters"})

    conn = db.get_connection()
    m = conn.execute("SELECT rank_level, name FROM libra_members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    if not m:
        return web.json_response({"success": False, "error": "Member not found"})

    target_level = m["rank_level"]
    if not db.user_can_manage_libra(user, target_level):
        return web.json_response({"success": False, "error": f"You do not have permission to change {m['name']}'s rank."})

    db.update_libra_member_rank(member_id, new_level, new_rank)
    return web.json_response({"success": True})

async def api_libra_member_kick(request: web.Request):
    user = require_user(request)
    data = await request.json()
    member_id = int(data.get("member_id", 0))
    if not member_id:
        return web.json_response({"success": False, "error": "Invalid member parameter"})

    conn = db.get_connection()
    m = conn.execute("SELECT rank_level, name FROM libra_members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    if not m:
        return web.json_response({"success": False, "error": "Member not found"})

    target_level = m["rank_level"]
    if not db.user_can_manage_libra(user, target_level):
        return web.json_response({"success": False, "error": f"You do not have permission to kick {m['name']}."})

    db.kick_libra_member(member_id)
    return web.json_response({"success": True})

async def api_libra_member_add(request: web.Request):
    user = require_user(request)
    if not db.user_can_manage_libra(user):
        return web.json_response({"success": False, "error": "Only Leader, Co-Leader, or Supervisor can add clan members."})

    data = await request.json()
    try:
        member_id = int(data.get("id", 0))
        if member_id <= 0:
            return web.json_response({"success": False, "error": "Valid In-Game ID is required"})
    except ValueError:
        return web.json_response({"success": False, "error": "ID must be a number"})

    name = str(data.get("name", "")).strip()
    if not name:
        return web.json_response({"success": False, "error": "Character name is required"})

    rank_level = int(data.get("rank_level", 7))
    rank_name = str(data.get("rank_name", "Trainee")).strip()
    db.add_libra_member(member_id, name, rank_level, rank_name)
    return web.json_response({"success": True})

async def api_libra_link_profile(request: web.Request):
    user = require_user(request)
    data = await request.json()
    member_id = int(data.get("member_id", 0))
    if not member_id:
        return web.json_response({"success": False, "error": "Invalid member ID"})
    db.link_libra_member(member_id, user["id"], user["username"])
    return web.json_response({"success": True})

async def api_user_link_profiles(request: web.Request):
    user = require_user(request)
    try:
        data = await request.json()
        libra_id = data.get("libra_member_id")
        try:
            libra_id = int(libra_id) if libra_id and str(libra_id) != "0" else None
        except ValueError:
            libra_id = None
        grand_name = str(data.get("grand_name", "")).strip() or user["username"]
        grand_rank = str(data.get("grand_rank", "")).strip() or "Family Member (Rank 1)"
        db.link_user_profiles(user["id"], user["username"], libra_id, grand_name, grand_rank)
        return web.json_response({"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)})

async def api_libra_member_warn(request: web.Request):
    user = require_user(request)
    data = await request.json()
    member_id = int(data.get("member_id", 0))
    reason = str(data.get("reason", "")).strip()
    if not member_id or not reason:
        return web.json_response({"success": False, "error": "Member ID and reason required."})

    conn = db.get_connection()
    m = conn.execute("SELECT rank_level, name FROM libra_members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    if not m:
        return web.json_response({"success": False, "error": "Member not found"})

    target_level = m["rank_level"]
    if not db.user_can_manage_libra(user, target_level):
        return web.json_response({"success": False, "error": f"You do not have permission to discipline {m['name']}."})

    res = db.add_libra_warning(member_id, reason, issued_by=user["username"])
    return web.json_response(res)

async def api_libra_member_clear_warn(request: web.Request):
    user = require_user(request)
    data = await request.json()
    member_id = int(data.get("member_id", 0))
    if not member_id:
        return web.json_response({"success": False, "error": "Member ID required."})

    conn = db.get_connection()
    m = conn.execute("SELECT rank_level, name FROM libra_members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    if not m:
        return web.json_response({"success": False, "error": "Member not found"})

    target_level = m["rank_level"]
    if not db.user_can_manage_libra(user, target_level):
        return web.json_response({"success": False, "error": f"You do not have permission to clear warnings for {m['name']}."})

    db.clear_libra_warnings(member_id)
    return web.json_response({"success": True})

async def api_libra_member_warnings(request: web.Request):
    require_user(request)
    member_id = request.query.get("member_id")
    if not member_id:
        return web.json_response({"success": False, "error": "Member ID required"})
    try:
        mid = int(member_id)
    except ValueError:
        return web.json_response({"success": False, "error": "Invalid ID"})

    warns = db.get_libra_warnings(mid)
    return web.json_response({"success": True, "warnings": warns})

async def api_user_dossier(request: web.Request):
    user = require_user(request)
    try:
        data = await request.json()
        db.update_user_dossier(user["id"], data)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def api_user_dismiss_profile_prompt(request: web.Request):
    user = require_user(request)
    db.dismiss_user_profile_prompt(user["id"])
    return web.json_response({"success": True})

async def handle_logo(request: web.Request):
    logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")
    if os.path.exists(logo_path):
        return web.FileResponse(logo_path)
    return web.Response(status=404)

def create_web_app():
    app = web.Application()

    # Static Assets & Pages
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.router.add_static("/static/", static_dir)

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
    app.router.add_post("/api/libra/member/rank", api_libra_member_rank)
    app.router.add_post("/api/libra/member/kick", api_libra_member_kick)
    app.router.add_post("/api/libra/member/add", api_libra_member_add)
    app.router.add_post("/api/libra/link_profile", api_libra_link_profile)
    app.router.add_post("/api/libra/member/warn", api_libra_member_warn)
    app.router.add_post("/api/libra/member/clear_warn", api_libra_member_clear_warn)
    app.router.add_get("/api/libra/member/warnings", api_libra_member_warnings)
    app.router.add_post("/api/user/link_profiles", api_user_link_profiles)
    app.router.add_post("/api/user/dossier", api_user_dossier)
    app.router.add_post("/api/user/dismiss_profile_prompt", api_user_dismiss_profile_prompt)

    return app
