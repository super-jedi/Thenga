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
SECRET_KEY = db.get_or_create_session_secret()

def get_client_secret() -> str:
    return os.getenv("DISCORD_CLIENT_SECRET", "").strip()

def create_session_token(user_data: dict) -> str:
    raw = json.dumps(user_data).encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()
    token = f"{base64.urlsafe_b64encode(raw).decode()}.{sig}"
    try:
        db.save_user_session(
            token,
            user_data.get("id", "0"),
            user_data.get("username", "Member"),
            user_data.get("avatar_url", ""),
            days=90
        )
    except Exception as e:
        print(f"Error persisting user session to SQLite: {e}")
    return token

def parse_session_token(token: str) -> Optional[dict]:
    if not token or not isinstance(token, str):
        return None
    try:
        raw_b64, sig = token.split(".")
        raw = base64.urlsafe_b64decode(raw_b64.encode())
        expected_sig = hmac.new(SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    
    # Secondary persistent lookup: check user_sessions table in SQLite
    try:
        sess = db.get_user_session(token)
        if sess:
            return sess
    except Exception:
        pass
    return None

def get_current_user(request: web.Request) -> Optional[dict]:
    # 1. Primary: HttpOnly Cookie
    cookie = request.cookies.get("thenga_user")
    if cookie:
        u = parse_session_token(cookie)
        if u:
            return u
    # 2. Authorization Header (Bearer token)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        u = parse_session_token(token)
        if u:
            return u
    # 3. Query Parameter (?session_token=...)
    q_token = request.query.get("session_token")
    if q_token:
        u = parse_session_token(q_token)
        if u:
            return u
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
    else:
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>OAuth Configuration Required</title>
    <style>
        body { background: #07080c; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .box { background: #0e121d; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 14px; padding: 32px; max-width: 480px; text-align: center; }
        h2 { color: #f87171; margin-top: 0; font-size: 20px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
        code { background: #181d2d; padding: 4px 8px; border-radius: 6px; color: #38bdf8; font-size: 13px; font-family: monospace; }
        a { color: #818cf8; text-decoration: none; display: inline-block; margin-top: 16px; font-weight: 600; }
    </style>
</head>
<body>
    <div class="box">
        <h2>🔒 Discord OAuth Setup Required</h2>
        <p>Discord OAuth is not yet configured for this host.</p>
        <p>Please add <code>DISCORD_CLIENT_SECRET=your_secret_here</code> to your <code>.env</code> file on the server and restart the bot.</p>
        <a href="/">← Return to Homepage</a>
    </div>
</body>
</html>"""
        return web.Response(text=html, status=503, content_type="text/html")

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
    response.set_cookie("thenga_user", token, max_age=86400 * 90, httponly=True, samesite="Lax", path="/")
    return response

async def handle_logout(request: web.Request):
    cookie = request.cookies.get("thenga_user")
    if cookie:
        db.delete_user_session(cookie)
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Signing out...</title>
    <script>
        try {
            localStorage.clear();
            sessionStorage.clear();
        } catch(e) {}
        window.location.replace('/');
    </script>
</head>
<body style="background:#07080c; color:#94a3b8; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;">
    <p>Signing out...</p>
</body>
</html>"""
    response = web.Response(text=html, content_type="text/html")
    response.del_cookie("thenga_user", path="/")
    return response

# ==========================================
# HTML TEMPLATES & PAGES
# ==========================================
COMMON_CSS = """
:root {
    --bg-page: #07080c;
    --bg-sidebar: #0b0e17;
    --bg-card: #0e121d;
    --bg-card-hover: #131724;
    --bg-input: #090b12;
    --border-subtle: #1a2030;
    --border-highlight: #252f47;
    --accent-emerald: #22c55e;
    --accent-emerald-glow: rgba(34, 197, 94, 0.25);
    --accent-crimson: #ef4444;
    --accent-crimson-hover: #dc2626;
    --accent-crimson-glow: rgba(239, 68, 68, 0.35);
    --accent-gold: #f59e0b;
    --accent-gold-glow: rgba(245, 158, 11, 0.25);
    --accent-blue: #3b82f6;
    --accent-purple: #a855f7;
    --text-white: #ffffff;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    
    /* Legacy aliases */
    --bg-dark: #07080c;
    --card-bg: #0e121d;
    --card-border: #1a2030;
    --accent: #ef4444;
    --accent-hover: #dc2626;
    --accent-glow: rgba(239, 68, 68, 0.35);
    --gold: #f59e0b;
    --tender-green: #22c55e;
    --green-glow: rgba(34, 197, 94, 0.25);
    --cyan: #06b6d4;
    --red: #ef4444;
    --purple: #a855f7;
    --text-primary: #ffffff;
    --text-secondary: #94a3b8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background-color: var(--bg-page);
    color: var(--text-white);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

/* APP SHELL & LAYOUT */
.app-shell {
    display: flex;
    min-height: 100vh;
    width: 100%;
}
.app-sidebar {
    width: 240px;
    flex-shrink: 0;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border-subtle);
    display: flex;
    flex-direction: column;
    position: sticky;
    top: 0;
    height: 100vh;
    z-index: 100;
}
.sidebar-brand {
    padding: 20px;
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
}
.sidebar-logo {
    width: 32px;
    height: 32px;
    object-fit: contain;
    filter: drop-shadow(0 2px 8px rgba(34, 197, 94, 0.4));
}
.sidebar-title {
    font-size: 16px;
    font-weight: 900;
    color: #fff;
    letter-spacing: 0.5px;
}
.sidebar-nav {
    flex: 1;
    padding: 16px 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    overflow-y: auto;
}
.nav-section-label {
    font-size: 10px;
    font-weight: 800;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 14px 14px 4px;
}
.nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 8px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 13px;
    font-weight: 600;
    transition: all 0.15s ease;
}
.nav-item:hover {
    background: rgba(255, 255, 255, 0.04);
    color: #fff;
}
.nav-item.active {
    background: rgba(34, 197, 94, 0.12);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.3);
    font-weight: 700;
}
.nav-icon {
    font-size: 16px;
    width: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.app-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
}
.top-header {
    height: 70px;
    background: rgba(11, 14, 23, 0.85);
    backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 32px;
    position: sticky;
    top: 0;
    z-index: 40;
}
.header-title-box h1 {
    font-size: 19px;
    font-weight: 900;
    color: #fff;
    letter-spacing: -0.3px;
}
.header-title-box p {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 2px;
}
.header-controls {
    display: flex;
    align-items: center;
    gap: 14px;
    position: relative;
}
.icon-btn {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 50%;
    width: 38px;
    height: 38px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    cursor: pointer;
    position: relative;
    transition: all 0.15s;
}
.icon-btn:hover {
    background: var(--bg-card-hover);
    color: #fff;
    border-color: var(--border-highlight);
}
.badge-dot {
    position: absolute;
    top: 7px;
    right: 7px;
    width: 8px;
    height: 8px;
    background: var(--accent-emerald);
    border-radius: 50%;
    box-shadow: 0 0 6px var(--accent-emerald);
}
.user-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    padding: 5px 14px 5px 6px;
    border-radius: 9999px;
    cursor: pointer;
    transition: all 0.15s;
}
.user-pill:hover {
    background: var(--bg-card-hover);
    border-color: var(--border-highlight);
}
.user-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    object-fit: cover;
    border: 1.5px solid var(--accent-emerald);
}
.dropdown-menu {
    position: absolute;
    top: 54px;
    right: 0;
    width: 280px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    box-shadow: 0 16px 40px rgba(0,0,0,0.7);
    padding: 12px;
    z-index: 200;
    display: none;
}
.dropdown-menu.open {
    display: block;
}
.dropdown-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 13px;
    font-weight: 600;
    transition: all 0.15s;
    cursor: pointer;
    border: none;
    background: transparent;
    width: 100%;
    text-align: left;
}
.dropdown-item:hover {
    background: rgba(255,255,255,0.06);
    color: #fff;
}
.content-body {
    flex: 1;
    padding: 32px;
    max-width: 1440px;
    width: 100%;
    margin: 0 auto;
}

/* HUB LAYOUT */
.hub-layout {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 28px;
    align-items: start;
}
.hub-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 24px;
}
.server-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 24px;
    cursor: pointer;
    transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    text-decoration: none;
    color: inherit;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.server-card:hover {
    transform: translateY(-3px);
    border-color: var(--border-highlight);
    box-shadow: 0 8px 30px rgba(0,0,0,0.5);
}
.server-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}
.server-title {
    font-size: 20px;
    font-weight: 800;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 8px;
}
.metrics-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    padding-top: 16px;
    border-top: 1px solid var(--border-subtle);
}
.metric-box .metric-label {
    font-size: 11px;
    color: var(--text-dim);
    font-weight: 700;
    text-transform: uppercase;
}
.metric-box .metric-val {
    font-size: 17px;
    font-weight: 800;
    color: #fff;
    margin-top: 2px;
}
.metric-box .metric-trend {
    font-size: 11px;
    font-weight: 700;
    color: var(--accent-emerald);
}

/* RECENT ACTIVITY */
.activity-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 24px;
}
.activity-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
}
.act-item {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px 0;
    border-bottom: 1px solid var(--border-subtle);
}
.act-item:last-child {
    border-bottom: none;
}
.act-icon {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    flex-shrink: 0;
}
.act-title {
    font-size: 14px;
    font-weight: 700;
    color: #fff;
}
.act-desc {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 2px;
}
.act-time {
    font-size: 11px;
    color: var(--text-dim);
    white-space: nowrap;
    margin-left: auto;
}

/* RIGHT RAIL & PROFILE */
.right-rail-wrap {
    display: flex;
    flex-direction: column;
    gap: 20px;
}
.profile-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 20px;
}
.persona-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    border-radius: 10px;
    background: #090a10;
    border: 1px solid var(--border-subtle);
    margin-top: 10px;
    cursor: pointer;
    transition: all 0.15s;
}
.persona-item:hover {
    border-color: var(--border-highlight);
    background: #0c0f18;
}
.persona-avatar {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: #1a2233;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
}
.persona-tag {
    font-size: 10px;
    font-weight: 800;
    background: rgba(34, 197, 94, 0.15);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.35);
    padding: 2px 8px;
    border-radius: 9999px;
    margin-left: auto;
}

/* BUTTONS */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px 18px;
    font-weight: 800;
    font-size: 13px;
    border-radius: 8px;
    cursor: pointer;
    border: none;
    text-decoration: none;
    transition: all 0.2s;
    letter-spacing: 0.3px;
}
.btn-primary { 
    background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); 
    color: #fff; 
    box-shadow: 0 4px 14px rgba(239, 68, 68, 0.35);
}
.btn-primary:hover { 
    background: linear-gradient(135deg, #f87171 0%, #dc2626 100%); 
    box-shadow: 0 0 20px var(--accent-crimson-glow); 
    transform: translateY(-1px);
}
.btn-green { 
    background: linear-gradient(135deg, #22c55e 0%, #15803d 100%); 
    color: white; 
    box-shadow: 0 4px 14px rgba(34, 197, 94, 0.25);
}
.btn-green:hover { 
    box-shadow: 0 0 15px var(--accent-emerald-glow); 
    transform: translateY(-1px);
}
.btn-red { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); color: white; }
.btn-purple { background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); color: white; }
.btn-secondary { background: #1a202c; color: white; border: 1px solid var(--border-subtle); }
.btn-secondary:hover { background: #242c3d; }
.btn-sm { padding: 6px 12px !important; font-size: 11px !important; }

/* TABS */
.tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 12px;
}
.tab-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 14px;
    font-weight: 700;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
}
.tab-btn.active { 
    background: rgba(34, 197, 94, 0.12); 
    color: #4ade80; 
    border: 1px solid rgba(34, 197, 94, 0.35);
}

/* CARDS & STATS */
.card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 24px;
    box-shadow: 0 4px 25px rgba(0, 0, 0, 0.45);
}
.stat-val { font-size: 26px; font-weight: 900; color: #fff; margin-top: 4px; }
.stat-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; font-weight: 800; letter-spacing: 0.8px; }

/* INPUTS & FORMS */
input, select, textarea {
    width: 100%;
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    color: #fff;
    padding: 12px;
    border-radius: 8px;
    font-size: 14px;
    margin-top: 6px;
    margin-bottom: 14px;
    transition: border-color 0.2s, box-shadow 0.2s;
    font-family: inherit;
}
input:focus, select:focus, textarea:focus { 
    outline: none; 
    border-color: var(--accent-emerald); 
    box-shadow: 0 0 12px var(--accent-emerald-glow); 
}

/* TABLES */
table { width: 100%; border-collapse: collapse; }
.table-responsive {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin-top: 10px;
    border-radius: 8px;
}
th, td { padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border-subtle); font-size: 13px; white-space: nowrap; }
th { color: var(--text-dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 800; }

/* BADGES */
.badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 9999px; font-size: 11px; font-weight: 800; letter-spacing: 0.4px; }
.badge-red { background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
.badge-green { background: rgba(34, 197, 94, 0.18); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); }
.badge-purple { background: rgba(168, 85, 247, 0.18); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
.badge-gold { background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }

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
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    position: relative;
}
.grand-veh-card:hover {
    transform: translateY(-4px);
    border-color: var(--accent-blue);
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
    border-bottom: 1px solid var(--border-subtle);
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
.grand-veh-plate-wrap { margin-bottom: 8px; }
.grand-veh-notes {
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 14px;
    min-height: 18px;
}
.grand-veh-actions {
    display: flex;
    gap: 8px;
    margin-top: auto;
}

/* MODAL SYSTEM */
.modal-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.78);
    backdrop-filter: blur(8px);
    z-index: 1000;
    justify-content: center;
    align-items: center;
    padding: 16px;
}
.modal-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 28px;
    max-width: 520px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0,0,0,0.85);
    position: relative;
    max-height: 90vh;
    overflow-y: auto;
}
.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
}
.modal-title {
    font-size: 19px;
    font-weight: 900;
    color: #fff;
}
.modal-close-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 20px;
    cursor: pointer;
    line-height: 1;
}
.modal-close-btn:hover { color: #fff; }

/* TOAST NOTIFICATION */
#toast-box {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #0f172a;
    border: 1.5px solid var(--accent-emerald);
    color: #fff;
    padding: 12px 20px;
    border-radius: 10px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.7);
    font-size: 14px;
    font-weight: 700;
    z-index: 9999;
    display: none;
    align-items: center;
    gap: 10px;
}

/* MOBILE BOTTOM NAV */
.mobile-bottom-nav {
    display: none;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 64px;
    background: rgba(11, 14, 23, 0.96);
    backdrop-filter: blur(16px);
    border-top: 1px solid var(--border-subtle);
    z-index: 90;
    justify-content: space-around;
    align-items: center;
}
.mobile-nav-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 11px;
    font-weight: 700;
    border: none;
    background: transparent;
    cursor: pointer;
}
.mobile-nav-btn.active {
    color: var(--accent-emerald);
}
.mobile-nav-btn span {
    font-size: 18px;
}

/* DOSSIER & IN-GAME ACTION STYLES */
.dossier-card {
    background: #0c0e15;
    border: 1px solid #1c202d;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    transition: transform 0.15s, border-color 0.15s;
    position: relative;
}
.dossier-card:hover {
    transform: translateY(-2px);
}
.card-grand {
    border-left: 3.5px solid #3b82f6 !important;
    border-color: rgba(59, 130, 246, 0.4);
}
.card-libra {
    border-left: 3.5px solid #a855f7 !important;
    border-color: rgba(168, 85, 247, 0.4);
}
.card-discord {
    border-left: 3.5px solid #5865F2 !important;
    border-color: rgba(88, 101, 242, 0.4);
}
.dossier-label {
    font-size: 10px;
    font-weight: 800;
    color: #64748b;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-top: 8px;
}
.dossier-val {
    font-size: 12.5px;
    line-height: 1.4;
    margin-top: 2px;
}
.dossier-edit-btn {
    background: rgba(255,255,255,0.06);
    border: 1px solid #272c3d;
    color: #94a3b8;
    cursor: pointer;
    font-size: 11px;
    padding: 3px 7px;
    border-radius: 5px;
    transition: all 0.15s;
}
.dossier-edit-btn:hover {
    color: #fff;
    background: #272c3d;
    border-color: #3b445f;
}
.ingame-btn-action {
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
}
.ingame-btn-action:hover {
    background: #ef4444;
    color: #fff;
    box-shadow: 0 0 10px rgba(239,68,68,0.5);
}
.ingame-btn-action.btn-kick:hover {
    background: #b91c1c;
}
.ingame-btn-action.btn-warn {
    border-color: #f59e0b;
    color: #fbbf24;
}
.ingame-btn-action.btn-warn:hover {
    background: #f59e0b;
    color: #000;
    box-shadow: 0 0 10px rgba(245,158,11,0.5);
}
.ingame-btn-claim {
    background: rgba(34, 197, 94, 0.15);
    border: 1.5px solid #22c55e;
    color: #4ade80;
    font-size: 11px;
    font-weight: 800;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
}
.ingame-btn-claim:hover {
    background: #22c55e;
    color: #fff;
}
.quick-stat-card {
    background: #0b0d14;
    border: 1px solid #1a1e2b;
    border-radius: 12px;
    padding: 16px 20px;
    cursor: pointer;
    transition: all 0.2s;
}
.quick-stat-card:hover {
    border-color: #ef4444;
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.5);
}
.subtabs-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 12px;
    overflow-x: auto;
    scrollbar-width: none;
}
.subtab-pill {
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    color: var(--text-muted);
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
    text-decoration: none;
}
.subtab-pill:hover {
    color: #fff;
    border-color: var(--border-highlight);
}
.subtab-pill.active {
    background: rgba(239,68,68,0.14);
    color: #fff;
    border-color: #ef4444;
}

/* RESPONSIVE BREAKPOINTS */
/* TABLET VIEW: 769px - 1080px */
@media (min-width: 769px) and (max-width: 1080px) {
    .app-sidebar {
        width: 72px;
    }
    .sidebar-title, .brand-text, .nav-label, .nav-section-label {
        display: none !important;
    }
    .sidebar-brand {
        justify-content: center;
        padding: 16px 0;
    }
    .nav-item {
        justify-content: center;
        padding: 12px 0;
        margin: 4px 8px;
    }
    .content-body {
        padding: 24px 20px;
    }
    .hub-layout {
        grid-template-columns: 1fr !important;
        gap: 20px;
    }
    .hub-grid {
        grid-template-columns: 1fr 1fr;
    }
    .right-rail-wrap {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
    }
}

/* MOBILE VIEW: <= 768px / 390px */
@media (max-width: 768px) {
    .app-sidebar {
        display: none !important;
    }
    .mobile-bottom-nav {
        display: flex !important;
    }
    .top-header {
        padding: 0 16px;
        height: 60px;
    }
    .header-title-box h1 {
        font-size: 16px;
    }
    .header-title-box p {
        display: none;
    }
    .content-body {
        padding: 16px 12px 84px 12px !important;
    }
    .hub-layout {
        grid-template-columns: 1fr !important;
        gap: 16px;
    }
    .hub-grid {
        grid-template-columns: 1fr !important;
        gap: 14px;
    }
    .metrics-row {
        gap: 8px;
    }
    .metric-box .metric-val {
        font-size: 15px;
    }
    .grand-veh-grid {
        grid-template-columns: 1fr !important;
    }
    .right-rail-wrap {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }
    .modal-card {
        padding: 20px 16px;
    }
}
"""

def render_header(user: dict, subtitle: str = "") -> str:
    """Backward compatibility header helper"""
    sub_tag = (
        f'<span style="font-size:14px; color:#94a3b8; font-weight:600;">/ {subtitle}</span>'
        if subtitle else
        '<span class="badge badge-green" style="font-size:10px;">MALAYALI CLUB</span>'
    )
    return f"""
    <header class="top-header" style="position:relative;">
        <a href="/" class="brand" style="text-decoration:none; display:flex; align-items:center; gap:10px;">
            <img src="/logo.png" alt="Thenga Logo" style="height:32px; width:auto; object-fit:contain; filter:drop-shadow(0 2px 8px rgba(34,197,94,0.4));">
            <span style="font-weight:900; color:#fff; font-size:16px;">THENGA <span style="color:var(--accent-emerald);">NETWORK</span></span> {sub_tag}
        </a>
        <div class="user-pill" onclick="toggleUserDropdown()">
            <img class="user-avatar" src="{user['avatar_url']}">
            <span style="font-weight:700; color:#fff; font-size:13px;">{user['username']}</span>
            <a href="/auth/logout" class="logout-btn" style="color:#ef4444; font-size:12px; margin-left:6px; text-decoration:none;">Logout</a>
        </div>
    </header>
    """

def render_app_shell(
    user: dict,
    active_nav: str,
    page_title: str,
    page_subtitle: str,
    main_content: str,
    right_rail: Optional[str] = None,
    extra_modals: str = "",
    extra_scripts: str = ""
) -> str:
    """
    Renders the full responsive layout shell matching the Figma Redesign:
    - 240px Navigation Rail on Desktop
    - 72px Icon Rail on Tablet (768px-1080px)
    - Mobile layout with top bar & bottom navigation bar (<= 768px)
    - Embeds all 6 Figma interaction modals
    """
    profile = db.get_user_profile(user["id"], user["username"])
    is_adm = is_admin_user(user)
    members = db.get_libra_members()
    grand_name = profile.get("grand_member_name") or user["username"]
    grand_rank = profile.get("grand_rank") or "Family Member (Rank 1)"
    libra_rank = profile.get("libra_rank") or "Associate (Rank 1)"
    primary_persona = profile.get("primary_persona") or "grandrp"
    libra_m = db.get_libra_member_by_discord(user["id"])
    libra_name = libra_m["name"] if libra_m else (profile.get("libra_member_name") or user["username"])
    libra_id = libra_m["id"] if libra_m else (profile.get("libra_member_id") or "Unlinked")

    # First time member dropdown options for personas modal
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

    # Navigation active states
    nav_hub = "active" if active_nav == "hub" else ""
    nav_grand = "active" if active_nav == "grand" else ""
    nav_libra = "active" if active_nav == "libra" else ""

    role_badge = (
        '<span class="badge badge-red">👑 FOUNDER / ADMIN</span>'
        if is_adm else
        '<span class="badge badge-green">VERIFIED OPERATIVE</span>'
    )

    grand_primary_pill = '<span class="persona-tag">Primary persona</span>' if primary_persona == 'grandrp' else '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); setPrimaryPersona(\'grandrp\')">Set as primary</button>'
    libra_primary_pill = '<span class="persona-tag">Primary persona</span>' if primary_persona == 'librarp' else '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); setPrimaryPersona(\'librarp\')">Set as primary</button>'
    grand_drop_primary = '<span class="persona-tag">Primary</span>' if primary_persona == 'grandrp' else ''
    libra_drop_primary = '<span class="persona-tag">Primary</span>' if primary_persona == 'librarp' else ''
    grand_sel = 'selected' if primary_persona == 'grandrp' else ''
    libra_sel = 'selected' if primary_persona == 'librarp' else ''
    main_layout_html = f'<div class="hub-layout"><main>{main_content}</main><aside class="right-rail-wrap">{right_rail}</aside></div>' if right_rail else f'<main>{main_content}</main>'

    shell_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{page_title} • Thenga Network</title>
    <link rel="icon" type="image/png" href="/logo.png">
    <style>
        {COMMON_CSS}
    </style>
</head>
<body>
    <div class="app-shell">
        <!-- LEFT NAVIGATION RAIL (240px Desktop / 72px Tablet / Hidden Mobile) -->
        <aside class="app-sidebar">
            <a href="/" class="sidebar-brand">
                <img src="/logo.png" alt="Thenga" class="sidebar-logo">
                <span class="sidebar-title brand-text">THENGA</span>
            </a>
            <nav class="sidebar-nav">
                <a href="/" class="nav-item {nav_hub}">
                    <span class="nav-icon">📊</span>
                    <span class="nav-label">Operations Hub</span>
                </a>
                
                <div class="nav-section-label">SERVERS</div>
                <a href="/grand" class="nav-item {nav_grand}">
                    <span class="nav-icon">🌆</span>
                    <span class="nav-label">Grand RP • EN2</span>
                </a>
                <a href="/libra" class="nav-item {nav_libra}">
                    <span class="nav-icon">⚖️</span>
                    <span class="nav-label">Libra RP • Fedrix</span>
                </a>

                <div class="nav-section-label">MANAGEMENT</div>
                <a href="/grand?tab=treasury" class="nav-item">
                    <span class="nav-icon">💰</span>
                    <span class="nav-label">Treasury</span>
                </a>
                <a href="/grand?tab=fleet" class="nav-item">
                    <span class="nav-icon">🚗</span>
                    <span class="nav-label">Fleet</span>
                </a>
                <a href="/libra?tab=events" class="nav-item">
                    <span class="nav-icon">📅</span>
                    <span class="nav-label">Events</span>
                </a>
                <a href="/libra?tab=members" class="nav-item">
                    <span class="nav-icon">👥</span>
                    <span class="nav-label">People</span>
                </a>

                <div class="nav-section-label">SYSTEM</div>
                <a href="javascript:openPersonasModal()" class="nav-item">
                    <span class="nav-icon">🔗</span>
                    <span class="nav-label">Linked Personas</span>
                </a>
                <a href="javascript:openPersonasModal()" class="nav-item">
                    <span class="nav-icon">⚙️</span>
                    <span class="nav-label">Settings</span>
                </a>
            </nav>
        </aside>

        <!-- MAIN VIEWPORT CONTAINER -->
        <div class="app-main">
            <!-- TOP HEADER BAR -->
            <header class="top-header">
                <div class="header-title-box">
                    <h1>{page_title}</h1>
                    <p>{page_subtitle}</p>
                </div>
                <div class="header-controls">
                    <!-- Notification Bell -->
                    <button class="icon-btn" onclick="toggleNotificationDropdown()" title="Notifications">
                        <span>🔔</span>
                        <span class="badge-dot"></span>
                    </button>
                    <!-- Notification Dropdown -->
                    <div id="notificationDropdown" class="dropdown-menu">
                        <div style="font-size:12px; font-weight:800; color:#fff; margin-bottom:8px; border-bottom:1px solid var(--border-subtle); padding-bottom:6px;">
                            NOTIFICATIONS & ALERTS
                        </div>
                        <div style="font-size:12px; color:var(--text-muted); padding:6px 0;">
                            🟢 <b>Treasury Synchronized</b>: Live balance active across EN2 and Fedrix.
                        </div>
                        <div style="font-size:12px; color:var(--text-muted); padding:6px 0;">
                            🚗 <b>Fleet Check</b>: 31 GrandRP and 24 Libra vehicles insured.
                        </div>
                    </div>

                    <!-- User Profile Pill -->
                    <div class="user-pill" onclick="toggleUserDropdown()">
                        <img class="user-avatar" src="{user['avatar_url']}" onerror="this.src='/logo.png'">
                        <span style="font-weight:700; font-size:13px; color:#fff;">{user['username']}</span>
                        <span style="font-size:11px; color:var(--text-dim);">▼</span>
                    </div>

                    <!-- User Profile Dropdown Menu (Figma State 1) -->
                    <div id="userDropdown" class="dropdown-menu">
                        <div style="padding:4px 6px 10px; border-bottom:1px solid var(--border-subtle); margin-bottom:8px;">
                            <div style="font-weight:800; color:#fff; font-size:14px;">{user['username']}</div>
                            <div style="font-size:11px; color:var(--text-dim);">Discord ID: {user['id']}</div>
                            <div style="margin-top:6px;">{role_badge}</div>
                        </div>
                        <div style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase; padding:4px 8px;">
                            Linked Personas (2)
                        </div>
                        <div style="font-size:12px; color:var(--text-muted); padding:4px 8px; display:flex; justify-content:space-between; align-items:center;">
                            <span>🌆 Grand: {grand_name}</span>
                            {grand_drop_primary}
                        </div>
                        <div style="font-size:12px; color:var(--text-muted); padding:4px 8px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-subtle); margin-bottom:8px; padding-bottom:8px;">
                            <span>⚖️ Libra: {libra_name}</span>
                            {libra_drop_primary}
                        </div>
                        <button class="dropdown-item" onclick="openPersonasModal()">🔗 Manage Linked Personas</button>
                        <button class="dropdown-item" onclick="openPersonasModal()">⚙️ Account Settings</button>
                        <a href="/auth/logout" class="dropdown-item" style="color:#ef4444;">🚪 Sign out</a>
                    </div>
                </div>
            </header>

            <!-- MAIN CONTENT AREA -->
            <div class="content-body">
                {main_layout_html}
            </div>
        </div>

        <!-- MOBILE BOTTOM NAVIGATION (<= 768px) -->
        <nav class="mobile-bottom-nav">
            <a href="/" class="mobile-nav-btn {nav_hub}">
                <span>📊</span>
                Hub
            </a>
            <a href="/grand" class="mobile-nav-btn {nav_grand}">
                <span>🌆</span>
                Grand RP
            </a>
            <a href="/libra" class="mobile-nav-btn {nav_libra}">
                <span>⚖️</span>
                Libra RP
            </a>
            <button class="mobile-nav-btn" onclick="openPersonasModal()">
                <span>👤</span>
                Profile
            </button>
        </nav>
    </div>

    <!-- ==================== FIGMA MODALS & DIALOGS (figma_1_11) ==================== -->

    <!-- 1. LINKED PERSONAS MANAGER MODAL (Figma State 2) -->
    <div id="personasModal" class="modal-backdrop">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 class="modal-title">Linked personas</h2>
                    <p style="font-size:12px; color:var(--text-muted); margin-top:2px;">Manage your connected game identities across our supported servers.</p>
                </div>
                <button class="modal-close-btn" onclick="closeModal('personasModal')">✕</button>
            </div>

            <!-- Current Personas Summary -->
            <div style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase; margin-bottom:6px;">Your linked personas</div>
            <div class="persona-item" onclick="setPrimaryPersona('grandrp')">
                <div class="persona-avatar">🌆</div>
                <div>
                    <div style="font-weight:700; font-size:13px; color:#fff;">{grand_name}</div>
                    <div style="font-size:11px; color:var(--text-dim);">Grand RP • EN2 • {grand_rank}</div>
                </div>
                {grand_primary_pill}
            </div>

            <div class="persona-item" onclick="setPrimaryPersona('librarp')" style="margin-bottom:18px;">
                <div class="persona-avatar">⚖️</div>
                <div>
                    <div style="font-weight:700; font-size:13px; color:#fff;">{libra_name} (ID #{libra_id})</div>
                    <div style="font-size:11px; color:var(--text-dim);">Libra RP • Fedrix • {libra_rank}</div>
                </div>
                {libra_primary_pill}
            </div>

            <!-- Primary Persona Dropdown Selector -->
            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Primary persona</label>
            <select id="modal-primary-select" onchange="setPrimaryPersona(this.value)">
                <option value="grandrp" {grand_sel}>Grand RP — {grand_name}</option>
                <option value="librarp" {libra_sel}>Libra RP — {libra_name}</option>
            </select>

            <div style="border-top:1px solid var(--border-subtle); padding-top:14px; margin-top:6px;">
                <label style="font-size:11px; font-weight:800; color:var(--accent-blue); text-transform:uppercase;">Grand RP (EN2 Character):</label>
                <input id="modal-grand-name" type="text" value="{grand_name}" placeholder="Character Name (e.g. John Doe)">

                <label style="font-size:11px; font-weight:800; color:var(--accent-purple); text-transform:uppercase;">Libra RP (Fedrix Clan Character):</label>
                <select id="modal-libra-id">
                    {member_select_options}
                </select>
            </div>

            <div style="display:flex; gap:10px; margin-top:8px;">
                <button id="btn-save-personas-modal" class="btn btn-green" style="flex:1;" onclick="submitSavePersonas()">Save & Link personas</button>
                <button class="btn btn-secondary" onclick="closeModal('personasModal')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- 2. EDIT MEMBER RANK MODAL WITH DYNAMIC RESPONSIBILITIES PREVIEW (Figma State 3) -->
    <div id="editRankModal" class="modal-backdrop">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 class="modal-title">Edit member rank</h2>
                    <p id="rank-modal-member-name" style="font-size:12px; color:var(--text-muted); margin-top:2px;">Member: Aiden K.</p>
                </div>
                <button class="modal-close-btn" onclick="closeModal('editRankModal')">✕</button>
            </div>

            <div style="margin-bottom:12px;">
                <span style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Current rank:</span>
                <span id="rank-modal-current-badge" class="badge badge-purple" style="margin-left:6px;">Member</span>
            </div>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">New rank</label>
            <select id="rank-modal-select" onchange="onRankSelectChange(this.value)">
                <option value="1">Leader (Tier 1)</option>
                <option value="2">Co-Leader (Tier 2)</option>
                <option value="3">Supervisor (Tier 3)</option>
                <option value="4">Enforcer (Tier 4)</option>
                <option value="5">Pro (Tier 5)</option>
                <option value="6">Ranger (Tier 6)</option>
                <option value="7">Trainee (Tier 7)</option>
            </select>

            <!-- Responsibilities Preview Box -->
            <div style="background:#090b12; border:1px solid var(--border-subtle); border-radius:10px; padding:14px; margin-bottom:18px;">
                <div style="font-size:12px; font-weight:800; color:var(--accent-emerald); display:flex; align-items:center; gap:6px; margin-bottom:6px;">
                    <span>🛡️</span> Responsibilities (preview)
                </div>
                <ul id="rank-responsibilities-list" style="font-size:12px; color:var(--text-muted); line-height:1.6; padding-left:18px;">
                    <li>Manage clan members (invite, rank, remove)</li>
                    <li>Approve vehicle requests</li>
                    <li>Access clan reports and activity logs</li>
                </ul>
            </div>

            <input type="hidden" id="rank-modal-member-id" value="">
            <div style="display:flex; gap:10px;">
                <button class="btn btn-green" style="flex:1;" onclick="submitRankChangeFromModal()">Save changes</button>
                <button class="btn btn-secondary" onclick="closeModal('editRankModal')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- 3. REMOVE MEMBER DESTRUCTIVE CONFIRMATION MODAL (Figma State 4) -->
    <div id="removeMemberModal" class="modal-backdrop">
        <div class="modal-card">
            <div class="modal-header">
                <h2 class="modal-title">Remove member?</h2>
                <button class="modal-close-btn" onclick="closeModal('removeMemberModal')">✕</button>
            </div>

            <div style="background:rgba(239, 68, 68, 0.12); border:1px solid rgba(239, 68, 68, 0.4); border-radius:10px; padding:14px; margin-bottom:16px;">
                <div style="color:#ef4444; font-weight:800; font-size:13px; margin-bottom:4px;">⚠️ This removes member access to this clan.</div>
                <div style="color:#f87171; font-size:12px; line-height:1.4;">The member will lose access to clan features, vehicles, and internal records. This action cannot be undone.</div>
            </div>

            <div style="display:flex; align-items:center; gap:12px; background:#090b12; border:1px solid var(--border-subtle); border-radius:10px; padding:12px; margin-bottom:20px;">
                <div id="remove-member-avatar" style="width:36px; height:36px; border-radius:50%; background:#1e293b; display:flex; align-items:center; justify-content:center; font-weight:800; color:#fff;">CM</div>
                <div>
                    <div id="remove-member-name" style="font-weight:800; color:#fff; font-size:14px;">Citra M.</div>
                    <div id="remove-member-id" style="font-size:11px; color:var(--text-dim);">LB-55619</div>
                </div>
            </div>

            <input type="hidden" id="remove-modal-id" value="">
            <div style="display:flex; gap:10px;">
                <button class="btn btn-red" style="flex:1;" onclick="confirmRemoveMember()">Remove member</button>
                <button class="btn btn-secondary" onclick="closeModal('removeMemberModal')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- 4. ADD CLAN MEMBER MODAL (Figma State 5) -->
    <div id="addMemberModal" class="modal-backdrop">
        <div class="modal-card">
            <div class="modal-header">
                <h2 class="modal-title">Add clan member</h2>
                <button class="modal-close-btn" onclick="closeModal('addMemberModal')">✕</button>
            </div>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Game ID *</label>
            <input id="add-member-game-id" type="number" placeholder="e.g. 10293">

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Display name *</label>
            <input id="add-member-name" type="text" placeholder="e.g. Evan R.">

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Rank *</label>
            <select id="add-member-rank">
                <option value="7">Trainee (Tier 7)</option>
                <option value="6">Ranger (Tier 6)</option>
                <option value="5">Pro (Tier 5)</option>
                <option value="4">Enforcer (Tier 4)</option>
                <option value="3">Supervisor (Tier 3)</option>
                <option value="2">Co-Leader (Tier 2)</option>
            </select>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Discord username</label>
            <input id="add-member-discord" type="text" placeholder="e.g. evanr#4821">

            <div style="display:flex; gap:10px; margin-top:8px;">
                <button class="btn btn-green" style="flex:1;" onclick="submitAddClanMember()">Save changes</button>
                <button class="btn btn-secondary" onclick="closeModal('addMemberModal')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- 5. ADD VEHICLE MODAL WITH EXPIRY COUNTDOWN (Figma State 6) -->
    <div id="addVehicleModal" class="modal-backdrop">
        <div class="modal-card">
            <div class="modal-header">
                <h2 class="modal-title">Add vehicle</h2>
                <button class="modal-close-btn" onclick="closeModal('addVehicleModal')">✕</button>
            </div>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Server</label>
            <select id="add-veh-server">
                <option value="grandrp">Grand RP (EN2)</option>
                <option value="librarp">Libra RP (Fedrix)</option>
            </select>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Vehicle model *</label>
            <input id="add-veh-model" type="text" placeholder="e.g. Sultan RS">

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Plate *</label>
            <input id="add-veh-plate" type="text" placeholder="e.g. TN-8842">

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Rank requirement *</label>
            <select id="add-veh-rank">
                <option value="Member">Member</option>
                <option value="Pro">Pro</option>
                <option value="Enforcer">Enforcer</option>
                <option value="Supervisor">Supervisor</option>
                <option value="Leader">Leader</option>
            </select>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Insurance expiry *</label>
            <input id="add-veh-expiry" type="date" onchange="onInsuranceDateChange(this.value)">

            <div id="veh-insurance-countdown" style="display:none; background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.35); border-radius:8px; padding:8px 12px; margin-bottom:14px; font-size:12px; color:#fbbf24;">
                ℹ️ Insurance expires in <b id="veh-days-left">0</b> days.
            </div>

            <div style="display:flex; gap:10px; margin-top:8px;">
                <button class="btn btn-green" style="flex:1;" onclick="submitAddVehicle()">Save changes</button>
                <button class="btn btn-secondary" onclick="closeModal('addVehicleModal')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- 6. DISCIPLINARY WARNING MODAL -->
    <div id="warnMemberModal" class="modal-backdrop">
        <div class="modal-card">
            <div class="modal-header">
                <div>
                    <h2 class="modal-title">Disciplinary Warning</h2>
                    <p id="warn-modal-member-name" style="font-size:12px; color:var(--text-muted); margin-top:2px;">Target: Operative</p>
                </div>
                <button class="modal-close-btn" onclick="closeModal('warnMemberModal')">✕</button>
            </div>

            <div style="display:flex; gap:10px; margin-bottom:14px;">
                <div style="background:#090b12; border:1px solid var(--border-subtle); border-radius:8px; padding:10px 14px; flex:1;">
                    <div style="font-size:10px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">CURRENT STRIKES</div>
                    <div id="warn-modal-count-display" style="font-size:16px; font-weight:900; color:#f59e0b; margin-top:2px;">0/3 Warnings</div>
                </div>
            </div>

            <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Reason for Warning *</label>
            <textarea id="warn-modal-reason" rows="3" placeholder="State reason (e.g. Inactive during turf raid, Rule violation)..."></textarea>

            <input type="hidden" id="warn-modal-member-id" value="">
            <div style="display:flex; gap:10px; margin-top:10px;">
                <button class="btn btn-red" style="flex:1;" onclick="submitIssueWarning()">⚠️ Issue Warning</button>
                <button class="btn btn-secondary" onclick="submitClearAllWarnings()">Clear All</button>
            </div>
        </div>
    </div>

    <!-- TOAST NOTIFICATION CONTAINER -->
    <div id="toast-box"></div>

    {extra_modals}

    <!-- ==================== CLIENT SCRIPTS ==================== -->
    <script>
        // Responsibilities Matrix for Edit Rank Dialog (figma_1_11)
        const RANK_RESPONSIBILITIES = {{
            1: [
                "Overall clan leadership, final strategic decisions, external representation",
                "Full access: manage ranks, members, events, vehicles, and settings",
                "Unlimited access to clan treasury bank accounts",
                "Issue and expunge disciplinary warnings across all clan operatives"
            ],
            2: [
                "Strategic operations planning, leader deputation, squad oversight",
                "Manage clan members (invite, rank, remove)",
                "Approve vehicle requests and fleet allocations",
                "Access clan financial records, reports, and activity logs",
                "Issue disciplinary warnings to lower-ranked members"
            ],
            3: [
                "Lead operational squads, coordinate field missions, ensure clan discipline",
                "Manage squads, moderate clan activities, schedule events",
                "Assign operational tasks, manage field reports, invite recruits",
                "Issue strike 1 disciplinary warnings to Enforcers and Trainees"
            ],
            4: [
                "Active combat and tactical participation, uphold clan rules",
                "Access designated tier clan vehicles and weaponry",
                "Join scheduled operations, turf radars, and clan rallies"
            ],
            5: [
                "Regular operative standing, active field mission support",
                "Access standard family vehicles",
                "Participate in weekly community and clan activities"
            ],
            6: [
                "Junior clan operative on active probationary duty",
                "Access basic pool vehicles and communication channels"
            ],
            7: [
                "Clan recruit / trainee undergoing active onboarding",
                "Attend training sessions and learn operational protocol"
            ]
        }};

        function showToast(msg) {{
            let box = document.getElementById('toast-box');
            if (!box) return;
            box.innerText = msg;
            box.style.display = 'flex';
            setTimeout(() => {{ box.style.display = 'none'; }}, 3500);
        }}

        function openModal(id) {{
            let el = document.getElementById(id);
            if (el) el.style.display = 'flex';
        }}

        function closeModal(id) {{
            let el = document.getElementById(id);
            if (el) el.style.display = 'none';
        }}

        function toggleUserDropdown() {{
            let el = document.getElementById('userDropdown');
            if (el) el.classList.toggle('open');
            let notif = document.getElementById('notificationDropdown');
            if (notif) notif.classList.remove('open');
        }}

        function toggleNotificationDropdown() {{
            let el = document.getElementById('notificationDropdown');
            if (el) el.classList.toggle('open');
            let userMenu = document.getElementById('userDropdown');
            if (userMenu) userMenu.classList.remove('open');
        }}

        // Close dropdowns on outside click
        window.addEventListener('click', function(e) {{
            if (!e.target.closest('.user-pill') && !e.target.closest('#userDropdown')) {{
                let u = document.getElementById('userDropdown');
                if (u) u.classList.remove('open');
            }}
            if (!e.target.closest('.icon-btn') && !e.target.closest('#notificationDropdown')) {{
                let n = document.getElementById('notificationDropdown');
                if (n) n.classList.remove('open');
            }}
        }});

        function openPersonasModal() {{
            openModal('personasModal');
        }}

        async function setPrimaryPersona(server) {{
            try {{
                let res = await fetch('/api/user/set_primary_persona', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ server: server }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Primary persona switched to " + (server === 'grandrp' ? 'Grand RP (EN2)' : 'Libra RP (Fedrix)'));
                    setTimeout(() => location.reload(), 600);
                }}
            }} catch(e) {{
                alert("Error: " + e);
            }}
        }}

        async function submitSavePersonas() {{
            let btn = document.getElementById('btn-save-personas-modal');
            if (btn) btn.innerText = "⏳ Saving...";
            try {{
                let grandName = document.getElementById('modal-grand-name').value;
                let libraId = document.getElementById('modal-libra-id').value;
                let res = await fetch('/api/user/link_profiles', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ grand_name: grandName, libra_member_id: libraId }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Personas saved successfully!");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to save personas");
                    if (btn) btn.innerText = "Save & Link personas";
                }}
            }} catch(err) {{
                alert("Error: " + err);
                if (btn) btn.innerText = "Save & Link personas";
            }}
        }}

        function onRankSelectChange(lvl) {{
            let list = document.getElementById('rank-responsibilities-list');
            if (!list) return;
            let items = RANK_RESPONSIBILITIES[lvl] || ["Standard clan member privileges."];
            list.innerHTML = items.map(i => '<li>' + i + '</li>').join('');
        }}

        function openEditRankModal(memberId, name, currentLevel, currentRankName) {{
            document.getElementById('rank-modal-member-id').value = memberId;
            document.getElementById('rank-modal-member-name').innerText = "Member: " + name;
            document.getElementById('rank-modal-current-badge').innerText = currentRankName;
            document.getElementById('rank-modal-select').value = currentLevel;
            onRankSelectChange(currentLevel);
            openModal('editRankModal');
        }}

        async function submitRankChangeFromModal() {{
            let memberId = document.getElementById('rank-modal-member-id').value;
            let sel = document.getElementById('rank-modal-select');
            let newLevel = parseInt(sel.value);
            let newRankName = sel.options[sel.selectedIndex].text.split(' (')[0];
            try {{
                let res = await fetch('/api/libra/member/rank', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ member_id: memberId, new_level: newLevel, new_rank: newRankName }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Rank updated successfully!");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to update rank");
                }}
            }} catch(e) {{ alert("Error: " + e); }}
        }}

        function openKickModal(memberId, name, currentLevel) {{
            document.getElementById('remove-modal-id').value = memberId;
            document.getElementById('remove-member-name').innerText = name;
            document.getElementById('remove-member-id').innerText = "LB-" + memberId;
            let initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
            document.getElementById('remove-member-avatar').innerText = initials;
            openModal('removeMemberModal');
        }}

        async function confirmRemoveMember() {{
            let memberId = document.getElementById('remove-modal-id').value;
            try {{
                let res = await fetch('/api/libra/member/kick', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ member_id: memberId }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Member removed from clan.");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to remove member");
                }}
            }} catch(e) {{ alert("Error: " + e); }}
        }}

        function openAddClanMemberModal() {{
            openModal('addMemberModal');
        }}

        async function submitAddClanMember() {{
            let id = document.getElementById('add-member-game-id').value;
            let name = document.getElementById('add-member-name').value;
            let sel = document.getElementById('add-member-rank');
            let level = parseInt(sel.value);
            let rankName = sel.options[sel.selectedIndex].text.split(' (')[0];
            let discord = document.getElementById('add-member-discord').value;
            if (!id || !name) return alert("Game ID and Name are required");
            try {{
                let res = await fetch('/api/libra/member/add', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ id, name, rank_level: level, rank_name: rankName, discord_username: discord }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Clan member registered!");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to add member");
                }}
            }} catch(e) {{ alert("Error: " + e); }}
        }}

        function openAddVehicleModal(defaultServer) {{
            if (defaultServer) {{
                let s = document.getElementById('add-veh-server');
                if (s) s.value = defaultServer;
            }}
            openModal('addVehicleModal');
        }}

        function onInsuranceDateChange(val) {{
            let callout = document.getElementById('veh-insurance-countdown');
            let span = document.getElementById('veh-days-left');
            if (!val) {{
                if (callout) callout.style.display = 'none';
                return;
            }}
            let target = new Date(val);
            let today = new Date();
            let diffMs = target - today;
            let days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
            if (callout && span) {{
                span.innerText = days > 0 ? days : 0;
                callout.style.display = 'block';
            }}
        }}

        async function submitAddVehicle() {{
            let server = document.getElementById('add-veh-server').value;
            let name = document.getElementById('add-veh-model').value;
            let plate = document.getElementById('add-veh-plate').value;
            let rank = document.getElementById('add-veh-rank').value;
            let exp = document.getElementById('add-veh-expiry').value;
            if (!name) return alert("Vehicle model is required");
            let days = 0;
            if (exp) {{
                let target = new Date(exp);
                let diffMs = target - new Date();
                days = Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
            }}
            try {{
                let res = await fetch('/api/vehicle/add', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ server, name, plate, insurance_days: days, notes: 'Rank ' + rank + '+ Required' }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Vehicle registered to fleet!");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to register vehicle");
                }}
            }} catch(e) {{ alert("Error: " + e); }}
        }}

        function openWarnModal(memberId, name, warnings) {{
            document.getElementById('warn-modal-member-id').value = memberId;
            document.getElementById('warn-modal-member-name').innerText = "Target: " + name + " (ID #" + memberId + ")";
            document.getElementById('warn-modal-count-display').innerText = warnings + "/3 Warnings";
            document.getElementById('warn-modal-reason').value = "";
            openModal('warnMemberModal');
        }}

        async function submitIssueWarning() {{
            let memberId = document.getElementById('warn-modal-member-id').value;
            let reason = document.getElementById('warn-modal-reason').value;
            if (!reason) return alert("Reason for warning is required");
            try {{
                let res = await fetch('/api/libra/member/warn', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ member_id: memberId, reason: reason }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Disciplinary warning issued!");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to issue warning");
                }}
            }} catch(e) {{ alert("Error: " + e); }}
        }}

        async function submitClearAllWarnings() {{
            let memberId = document.getElementById('warn-modal-member-id').value;
            if (!confirm("Are you sure you want to clear all disciplinary warnings for this member?")) return;
            try {{
                let res = await fetch('/api/libra/member/clear_warn', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ member_id: memberId }})
                }});
                let d = await res.json();
                if (d.success) {{
                    showToast("Warnings cleared. Operative restored to Good Standing.");
                    setTimeout(() => location.reload(), 600);
                }} else {{
                    alert(d.error || "Failed to clear warnings");
                }}
            }} catch(e) {{ alert("Error: " + e); }}
        }}
    </script>
    {extra_scripts}
</body>
</html>
"""
    return shell_html

# ==========================================
# PAGE 1: LANDING & OPERATIONS HUB (/)
# ==========================================
async def handle_home(request: web.Request):
    user = get_current_user(request)

    if not user:
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thenga Network Management Dashboard</title>
    <link rel="icon" type="image/png" href="/logo.png">
    <style>
        {COMMON_CSS}
    </style>
</head>
<body style="justify-content: center; align-items: center; text-align: center; padding: 20px; background: radial-gradient(circle at 50% 20%, rgba(34, 197, 94, 0.12) 0%, rgba(7, 8, 12, 1) 75%); min-height: 100vh;">
    <div class="card" style="max-width: 480px; width: 100%; padding: 42px 36px; border: 1.5px solid var(--border-subtle); box-shadow: 0 16px 60px rgba(0, 0, 0, 0.8), 0 0 45px rgba(34, 197, 94, 0.12); border-radius: 20px;">
        <div style="margin-bottom: 22px;">
            <img src="/logo.png" alt="Thenga Network" style="max-width: 180px; width: 100%; height: auto; filter: drop-shadow(0 8px 30px rgba(34, 197, 94, 0.45));">
        </div>
        <h1 style="color: #fff; font-size: 23px; font-weight: 900; margin-bottom: 6px; letter-spacing: -0.5px; text-transform: uppercase;">
            Thenga Network <span style="color: var(--accent-emerald);">Dashboard</span>
        </h1>
        <p style="color: var(--text-muted); margin-bottom: 28px; font-size: 13px; line-height: 1.5;">
            Integrated command center for <b style="color: #4ade80;">Thenga Network Malayali Club</b>
        </p>
        <a href="/auth/login" class="btn" style="width: 100%; padding: 14px; font-size: 15px; font-weight: 800; background: #5865F2; color: #fff; border-radius: 10px; box-shadow: 0 4px 20px rgba(88, 101, 242, 0.45); text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 10px; transition: transform 0.15s, box-shadow 0.15s;">
            <svg style="width: 22px; height: 22px; fill: currentColor;" viewBox="0 0 24 24"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0a12.64 12.64 0 0 0-.617-1.25a.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10.2 10.2 0 0 0 .372-.292a.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127a12.299 12.299 0 0 1-1.873.894a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028a19.839 19.839 0 0 0 6.002-3.03a.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418z"/></svg>
            Login with Discord
        </a>
        
        <div style="margin-top: 22px; font-size: 11px; color: #64748b; display: flex; align-items: center; justify-content: center; gap: 6px;">
            <span>🔒</span> Verified Thenga Network Members Only • Sessions Persist 90 Days
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
    primary_persona = profile.get("primary_persona") or "grandrp"
    grand_name = profile.get("grand_member_name") or user["username"]
    libra_m = db.get_libra_member_by_discord(user["id"])
    libra_name = libra_m["name"] if libra_m else (profile.get("libra_member_name") or user["username"])
    libra_id = libra_m["id"] if libra_m else (profile.get("libra_member_id") or "Unlinked")

    # Fetch recent activities from SQLite
    activities = db.get_recent_activities(limit=10)
    activity_items_html = ""
    for act in activities:
        cat = act.get("category", "info").lower()
        if cat == "treasury":
            icon_badge = '<span class="act-icon" style="background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3);">💰</span>'
        elif cat == "fleet":
            icon_badge = '<span class="act-icon" style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(59,130,246,0.3);">🚗</span>'
        elif cat == "events":
            icon_badge = '<span class="act-icon" style="background:rgba(168,85,247,0.15); color:#c084fc; border:1px solid rgba(168,85,247,0.3);">📅</span>'
        elif cat == "warning":
            icon_badge = '<span class="act-icon" style="background:rgba(239,68,68,0.15); color:#f87171; border:1px solid rgba(239,68,68,0.3);">⚠️</span>'
        elif cat == "rank":
            icon_badge = '<span class="act-icon" style="background:rgba(245,158,11,0.15); color:#fbbf24; border:1px solid rgba(245,158,11,0.3);">🎖️</span>'
        else:
            icon_badge = '<span class="act-icon" style="background:rgba(148,163,184,0.15); color:#94a3b8; border:1px solid rgba(148,163,184,0.3);">👤</span>'

        created_str = str(act.get("created_at") or "Just now")
        activity_items_html += f"""
        <div class="act-item">
            {icon_badge}
            <div style="flex:1; min-width:0;">
                <div class="act-title">{act['title']}</div>
                <div class="act-desc">{act['description']}</div>
            </div>
            <div class="act-time">{created_str[:16]}</div>
        </div>
        """

    # Build Left Column Main Content (Server Cards + Activity Stream)
    main_content = f"""
    <!-- TOP SERVER STATUS CARDS (Figma Desktop 1080p Layout) -->
    <div class="hub-grid">
        <!-- Grand RP • EN2 Card -->
        <a href="/grand" class="server-card">
            <div>
                <div class="server-card-header">
                    <div class="server-title">
                        <span style="font-size:22px;">🌆</span>
                        Grand RP • EN2
                    </div>
                    <span class="badge badge-green">● Online</span>
                </div>
                <div class="metrics-row">
                    <div class="metric-box">
                        <div class="metric-label">Treasury</div>
                        <div class="metric-val">{format_money(grand_bal['balance'])}</div>
                        <div class="metric-trend">+2.8% (7d)</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Fleet</div>
                        <div class="metric-val">{len(grand_v)} Cars</div>
                        <div class="metric-trend">+3 (7d)</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Plantation</div>
                        <div class="metric-val" style="color:#34d399; font-size:15px;">Pineapple</div>
                        <div class="metric-trend" style="color:var(--text-dim);">Cycle #14</div>
                    </div>
                </div>
            </div>
            <div style="margin-top:16px; padding-top:12px; border-top:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:var(--text-muted); font-weight:700;">Open Command Center</span>
                <span style="color:#60a5fa; font-weight:800; font-size:14px;">→</span>
            </div>
        </a>

        <!-- Libra RP • Fedrix Card -->
        <a href="/libra" class="server-card">
            <div>
                <div class="server-card-header">
                    <div class="server-title">
                        <span style="font-size:22px;">⚖️</span>
                        Libra RP • Fedrix
                    </div>
                    <span class="badge badge-green">● Online</span>
                </div>
                <div class="metrics-row">
                    <div class="metric-box">
                        <div class="metric-label">Treasury</div>
                        <div class="metric-val">{format_money(libra_bal['balance'])}</div>
                        <div class="metric-trend">+1.4% (7d)</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Fleet</div>
                        <div class="metric-val">{len(libra_v)} Cars</div>
                        <div class="metric-trend">+1 (7d)</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">Events</div>
                        <div class="metric-val" style="color:#c084fc; font-size:15px;">3 Scheduled</div>
                        <div class="metric-trend" style="color:var(--text-dim);">28 Members</div>
                    </div>
                </div>
            </div>
            <div style="margin-top:16px; padding-top:12px; border-top:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; color:var(--text-muted); font-weight:700;">Open Command Center</span>
                <span style="color:#c084fc; font-weight:800; font-size:14px;">→</span>
            </div>
        </a>
    </div>

    <!-- RECENT ACTIVITY FEED (Figma Layout) -->
    <div class="activity-card">
        <div class="activity-header">
            <div>
                <h3 style="font-size:17px; font-weight:900; color:#fff;">Recent activity</h3>
                <p style="font-size:12px; color:var(--text-muted); margin-top:2px;">Real-time transaction and fleet stream across network servers</p>
            </div>
            <a href="javascript:showToast('Showing all recent network logs')" style="font-size:12px; font-weight:700; color:var(--accent-emerald); text-decoration:none;">View all &gt;</a>
        </div>
        <div class="activity-list">
            {activity_items_html}
        </div>
    </div>
    """

    # Build Right Column Rail (Profile + Linked Personas + Disciplinary Standing)
    right_rail = f"""
    <!-- Profile Card (figma_3_2_1080p) -->
    <div class="profile-card">
        <div style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase; margin-bottom:12px;">Profile</div>
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
            <img src="{user['avatar_url']}" style="width:48px; height:48px; border-radius:50%; border:2px solid var(--accent-emerald); object-fit:cover;" onerror="this.src='/logo.png'">
            <div>
                <div style="font-weight:900; font-size:15px; color:#fff;">{user['username']}</div>
                <div style="font-size:12px; color:var(--text-muted);">Network Administrator</div>
                <div style="margin-top:4px;">
                    <span class="badge {'badge-red' if is_adm else 'badge-green'}" style="font-size:10px;">{'Admin' if is_adm else 'Operative'}</span>
                </div>
            </div>
        </div>
        <button class="btn btn-secondary btn-sm" style="width:100%;" onclick="openPersonasModal()">
            ✏️ Edit profile
        </button>
    </div>

    <!-- Linked Personas Manager Card (figma_3_2_1080p & figma_1_11) -->
    <div class="profile-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Linked personas</span>
            <span style="font-size:11px; color:var(--text-muted); font-weight:700;">2 Connected</span>
        </div>

        <div class="persona-item" onclick="openPersonasModal()">
            <div class="persona-avatar">🌆</div>
            <div>
                <div style="font-weight:700; font-size:13px; color:#fff;">{grand_name}</div>
                <div style="font-size:11px; color:var(--text-dim);">Grand RP • EN2</div>
            </div>
            {'<span class="persona-tag">Primary</span>' if primary_persona == 'grandrp' else '<span style="color:var(--text-dim); font-size:13px; margin-left:auto;">&gt;</span>'}
        </div>

        <div class="persona-item" onclick="openPersonasModal()">
            <div class="persona-avatar">⚖️</div>
            <div>
                <div style="font-weight:700; font-size:13px; color:#fff;">{libra_name}</div>
                <div style="font-size:11px; color:var(--text-dim);">Libra RP • Fedrix</div>
            </div>
            {'<span class="persona-tag">Primary</span>' if primary_persona == 'librarp' else '<span style="color:var(--text-dim); font-size:13px; margin-left:auto;">&gt;</span>'}
        </div>

        <button class="btn btn-secondary btn-sm" style="width:100%; margin-top:12px; border-style:dashed;" onclick="openPersonasModal()">
            + Link persona
        </button>
    </div>

    <!-- Disciplinary Standing Card -->
    <div class="profile-card">
        <div style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase; margin-bottom:10px;">Disciplinary Record</div>
        <div style="font-size:12px; padding:6px 0; border-bottom:1px solid var(--border-subtle); display:flex; justify-content:space-between;">
            <span style="color:var(--text-muted);">Grand RP EN2:</span>
            <span style="color:#4ade80; font-weight:700;">{profile.get('grand_punishments') or 'Clean Record (0 Warnings)'}</span>
        </div>
        <div style="font-size:12px; padding:6px 0; border-bottom:1px solid var(--border-subtle); display:flex; justify-content:space-between;">
            <span style="color:var(--text-muted);">Libra Fedrix:</span>
            <span style="color:#4ade80; font-weight:700;">{profile.get('libra_punishments') or 'Good Standing (0 Suspensions)'}</span>
        </div>
        <div style="font-size:12px; padding:6px 0; display:flex; justify-content:space-between;">
            <span style="color:var(--text-muted);">Discord Server:</span>
            <span style="color:#4ade80; font-weight:700;">{profile.get('discord_punishments') or 'Clean Record'}</span>
        </div>
    </div>
    """

    return web.Response(
        text=render_app_shell(
            user=user,
            active_nav="hub",
            page_title="Operations Hub",
            page_subtitle="Manage your servers, finances, fleet and events across the Thenga network.",
            main_content=main_content,
            right_rail=right_rail
        ),
        content_type="text/html"
    )

# ==========================================
# PAGE 2: GRAND RP DASHBOARD (/grand)
# ==========================================
async def handle_grand(request: web.Request):
    user = get_current_user(request)
    if not user:
        return web.HTTPFound("/")

    req_tab = request.query.get("tab", "bank")
    if req_tab in ["fleet", "garage"]:
        active_tab = "garage"
    elif req_tab in ["plantation", "crops"]:
        active_tab = "plantation"
    else:
        active_tab = "bank"

    bal = db.get_bank_balance("grandrp")
    txs = db.get_recent_transactions("grandrp", limit=30)
    vehicles = db.get_vehicles("grandrp")
    plantation = db.get_plantation_state()

    # Build vehicles cards & table rows
    now = datetime.now(timezone.utc)
    veh_rows = ""
    veh_grid_cards = ""
    insured_count = 0
    expired_count = 0
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
                insured_count += 1
            else:
                expired_count += 1
        else:
            expired_count += 1

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
    plant_badge = '<span class="badge badge-green">GROWING</span>' if plant_status == 'GROWING' else '<span class="badge badge-red">IDLE</span>'

    grand_content = f"""
    <!-- SUB-TABS NAVIGATION BAR -->
    <div class="subtabs-bar">
        <button id="subtab-btn-bank" class="subtab-pill active" onclick="showSubTab('bank')">🏦 Family Treasury</button>
        <button id="subtab-btn-garage" class="subtab-pill" onclick="showSubTab('garage')">🏎️ Garage Fleet ({len(vehicles)} Cars)</button>
        <button id="subtab-btn-plantation" class="subtab-pill" onclick="showSubTab('plantation')">🍍 Pineapple Plantation</button>
    </div>

    <!-- TAB 1: FAMILY TREASURY -->
    <div id="tab-bank">
        <div class="grid-3" style="margin-bottom: 24px;">
            <div class="card" style="border-left: 3.5px solid #22c55e;">
                <div class="stat-label">Current Family Fund</div>
                <div class="stat-val" style="color:#22c55e;">{format_money(bal['balance'])}</div>
                <div style="font-size:11px; color:#22c55e; font-weight:700; margin-top:4px;">● Live GrandRP EN2 Balance</div>
            </div>
            <div class="card">
                <div class="stat-label">Total Deposited</div>
                <div class="stat-val" style="color:#10b981;">{format_money(bal['total_deposited'])}</div>
                <div style="font-size:11px; color:#64748b; margin-top:4px;">3% family deposit tax</div>
            </div>
            <div class="card">
                <div class="stat-label">Total Withdrawn</div>
                <div class="stat-val" style="color:#ef4444;">{format_money(bal['total_withdrawn'])}</div>
                <div style="font-size:11px; color:#64748b; margin-top:4px;">5% cash withdrawal tax</div>
            </div>
            <div class="card">
                <div class="stat-label">In-Game Taxes Absorbed</div>
                <div class="stat-val" style="color:#f59e0b;">{format_money(bal['total_tax_paid'])}</div>
                <div style="font-size:11px; color:#64748b; margin-top:4px;">Total tax retained</div>
            </div>
        </div>

        <div class="grid-2" style="margin-bottom: 30px;">
            <!-- Deposit Form -->
            <div class="card">
                <h3 style="color:#10b981; margin-bottom:12px;">📥 Deposit to Family Fund (3% Tax)</h3>
                <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Amount:</label>
                <input id="dep-amt" type="text" placeholder="1M or 500k" oninput="calcDeposit()">
                <div style="display:flex; gap:6px; margin-bottom:12px;">
                    <button class="btn btn-secondary btn-sm" onclick="setDepPreset('500k')">$500k</button>
                    <button class="btn btn-secondary btn-sm" onclick="setDepPreset('1M')">$1M</button>
                    <button class="btn btn-secondary btn-sm" onclick="setDepPreset('2.5M')">$2.5M</button>
                    <button class="btn btn-secondary btn-sm" onclick="setDepPreset('5M')">$5M</button>
                </div>
                <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Source / Reason:</label>
                <input id="dep-reason" type="text" placeholder="Plantation harvest, Car sales, Office tasks">
                <div id="dep-preview" style="font-size:13px; color:#94a3b8; margin-bottom:14px; background:#090b12; padding:8px 12px; border-radius:6px; border:1px solid #1c202d;">3% Tax: $0 | Net Added: $0</div>
                <button class="btn btn-green" style="width:100%;" onclick="submitDeposit('grandrp')">Confirm Deposit</button>
            </div>

            <!-- Withdraw Form -->
            <div class="card">
                <h3 style="color:#ef4444; margin-bottom:12px;">📤 Withdraw from Family Fund (5% Tax)</h3>
                <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Amount:</label>
                <input id="with-amt" type="text" placeholder="500k" oninput="calcWithdraw()">
                <div style="display:flex; gap:6px; margin-bottom:12px;">
                    <button class="btn btn-secondary btn-sm" onclick="setWithPreset('500k')">$500k</button>
                    <button class="btn btn-secondary btn-sm" onclick="setWithPreset('1M')">$1M</button>
                    <button class="btn btn-secondary btn-sm" onclick="setWithPreset('2.5M')">$2.5M</button>
                </div>
                <label style="font-size:11px; font-weight:800; color:var(--text-dim); text-transform:uppercase;">Reason / Purpose:</label>
                <input id="with-reason" type="text" placeholder="Family fines, Fleet expansion, Event budget">
                <div id="with-preview" style="font-size:13px; color:#94a3b8; margin-bottom:14px; background:#090b12; padding:8px 12px; border-radius:6px; border:1px solid #1c202d;">5% Tax: $0 | Net Cash Received: $0</div>
                <button class="btn btn-red" style="width:100%;" onclick="submitWithdraw('grandrp')">Confirm Withdrawal</button>
            </div>
        </div>

        <div class="card" style="padding:0; overflow:hidden; background:#0a0c12; border:1px solid #1a1e2b;">
            <div style="padding:16px 20px; border-bottom:1px solid #161924;">
                <h3 style="color:#fff; font-size:16px; margin:0;">📜 Recent Grand RP Transactions</h3>
            </div>
            <div class="table-responsive" style="margin:0;">
                <table style="margin:0;">
                    <thead>
                        <tr style="background:#08090d;">
                            <th>TYPE</th><th>GROSS</th><th>TAX</th><th>NET</th><th>MEMBER</th><th>REASON</th><th>DATE</th>
                        </tr>
                    </thead>
                    <tbody>{tx_rows}</tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- TAB 2: GARAGE FLEET -->
    <div id="tab-garage" style="display:none;">
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:20px;">
            <div class="card" style="padding:16px 20px;">
                <div class="stat-label">Fleet Count</div>
                <div class="stat-val" style="color:#fff;">{len(vehicles)} Cars</div>
                <div style="font-size:12px; color:#60a5fa; font-weight:700; margin-top:4px;">Grand RP EN2 Showroom</div>
            </div>
            <div class="card" style="padding:16px 20px;">
                <div class="stat-label">Active Insurance</div>
                <div class="stat-val" style="color:#22c55e;">{insured_count} Insured</div>
                <div style="font-size:12px; color:#94a3b8; margin-top:4px;">Valid GTA V registrations</div>
            </div>
            <div class="card" style="padding:16px 20px;">
                <div class="stat-label">Expired / Uninsured</div>
                <div class="stat-val" style="color:#ef4444;">{expired_count} Expired</div>
                <div style="font-size:12px; color:#f87171; margin-top:4px;">Needs 30d renewal</div>
            </div>
        </div>

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

        <div class="card" style="padding:16px 20px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:16px;">
                <div>
                    <h3 style="margin:0;">Grand RP Fleet ({len(vehicles)} Vehicles)</h3>
                    <div style="color:var(--text-secondary); font-size:13px; margin-top:2px;">Authentic GTA V GrandRP fleet showroom & custom license plates</div>
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
            <div id="garage-table-view" class="table-responsive" style="display:none; margin:0;">
                <table style="margin:0;">
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
        <div class="card" style="margin-bottom: 24px; border-left: 3.5px solid #eab308;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <div>
                    <h2 style="color:#fef08a; margin:0;">🍍 Pineapple Plantation Business</h2>
                    <p style="color:var(--text-secondary); margin-top:4px; font-size:13px;">Manage family pineapple crops, nourish cycles, and bank harvest earnings.</p>
                </div>
                {plant_badge}
            </div>

            <!-- Progress Stepper matching Figma -->
            <div style="display:flex; justify-content:space-between; align-items:center; background:#090b12; border:1px solid #1c202d; border-radius:10px; padding:16px 24px; margin-bottom:20px; overflow-x:auto;">
                <div style="text-align:center;">
                    <div style="font-size:20px;">🌱</div>
                    <div style="font-size:12px; font-weight:800; color:#22c55e;">1. Planted</div>
                    <div style="font-size:10px; color:#64748b;">Seed Sown</div>
                </div>
                <div style="flex:1; height:2px; background:#22c55e; margin:0 12px;"></div>
                <div style="text-align:center;">
                    <div style="font-size:20px;">💧</div>
                    <div style="font-size:12px; font-weight:800; color:#3b82f6;">2. Nourish</div>
                    <div style="font-size:10px; color:#64748b;">Water Every 2h</div>
                </div>
                <div style="flex:1; height:2px; background:#3b82f6; margin:0 12px;"></div>
                <div style="text-align:center;">
                    <div style="font-size:20px;">🍍</div>
                    <div style="font-size:12px; font-weight:800; color:#eab308;">3. Harvest Ready</div>
                    <div style="font-size:10px; color:#64748b;">Matures in 4h</div>
                </div>
                <div style="flex:1; height:2px; background:#475569; margin:0 12px;"></div>
                <div style="text-align:center;">
                    <div style="font-size:20px;">🏦</div>
                    <div style="font-size:12px; font-weight:800; color:#94a3b8;">4. Bank Profit</div>
                    <div style="font-size:10px; color:#64748b;">+Family Treasury</div>
                </div>
            </div>

            <div style="display:flex; flex-wrap:wrap; gap:12px;">
                <button class="btn btn-green" onclick="plantCrop()">🌱 Plant Pineapple (2h nourish, 4h harvest)</button>
                <button class="btn btn-primary" onclick="nourishCrop()">💧 Nourish Now (+2h)</button>
                <button class="btn btn-purple" onclick="harvestCrop()">🚜 Collect Harvest & Bank</button>
            </div>
        </div>
    </div>
    """

    grand_scripts = f"""
    function setDepPreset(val) {{
        document.getElementById('dep-amt').value = val;
        calcDeposit();
    }}
    function setWithPreset(val) {{
        document.getElementById('with-amt').value = val;
        calcWithdraw();
    }}

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

    function showSubTab(tab) {{
        document.getElementById('tab-bank').style.display = tab === 'bank' ? 'block' : 'none';
        document.getElementById('tab-garage').style.display = tab === 'garage' ? 'block' : 'none';
        document.getElementById('tab-plantation').style.display = tab === 'plantation' ? 'block' : 'none';
        
        document.querySelectorAll('.subtab-pill').forEach(b => b.classList.remove('active'));
        let activeBtn = document.getElementById('subtab-btn-' + tab);
        if (activeBtn) activeBtn.classList.add('active');
    }}

    // Activate initial tab from URL parameter
    showSubTab('{active_tab}');

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
        if (!confirm("Remove this vehicle from Grand RP family fleet?")) return;
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
    """

    html = render_app_shell(
        user=user,
        active_nav="grand",
        page_title="Grand RP • EN2 Operations",
        page_subtitle="Manage Family Fund, 31 Vehicles, and Pineapple Plantation Business",
        main_content=grand_content,
        right_rail=None,
        extra_scripts=grand_scripts
    )
    return web.Response(text=html, content_type="text/html")


# ==========================================
# PAGE 3: LIBRA RP DASHBOARD (/libra) - AUTHENTIC IN-GAME CLAN UI
# ==========================================
async def handle_libra(request: web.Request):
    user = get_current_user(request)
    if not user:
        return web.HTTPFound("/")

    req_tab = request.query.get("tab", "members")
    if req_tab in ["ranks", "hierarchy"]:
        active_tab = "ranks"
    elif req_tab in ["fleet", "vehicles"]:
        active_tab = "vehicles"
    elif req_tab in ["events", "radar"]:
        active_tab = "events"
    elif req_tab in ["treasury", "logs", "bank"]:
        active_tab = "logs"
    else:
        active_tab = "members"

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
            <button class="ingame-btn-action" onclick="openRankModal({mid}, \'{safe_name}\', {mlvl}, \'{mrname}\')">RANK</button>
            <button class="ingame-btn-action btn-warn" onclick="openWarnModal({mid}, \'{safe_name}\', {w_cnt})">WARN</button>
            <button class="ingame-btn-action btn-kick" onclick="openKickModal({mid}, \'{safe_name}\', {mlvl})">KICK</button>
            '''
        elif not m.get("discord_id") and is_first_time:
            actions_html = f'''
            <button class="ingame-btn-claim" onclick="claimLibraProfile({mid}, \'{safe_name}\')">CLAIM</button>
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
                <h3 style="color:#c084fc; font-size:18px; margin:0;">⚔️ {e['name']}</h3>
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
    grand_edit_btn = f'<button class="dossier-edit-btn" onclick="openDossierModal(\'grand\')" title="Edit Grand RP Dossier">✏️ Edit</button>' if can_manage else ''
    libra_edit_btn = f'<button class="dossier-edit-btn" onclick="openDossierModal(\'libra\')" title="Edit Libra RP Dossier">✏️ Edit</button>' if can_manage else ''
    discord_edit_btn = f'<button class="dossier-edit-btn" onclick="openDossierModal(\'discord\')" title="Edit Discord Dossier">✏️ Edit</button>' if can_manage else ''

    total_m_count = len(members)
    online_m_count = sum(1 for m in members if m.get("is_online"))

    add_btn_html = '''
    <button class="btn btn-primary btn-sm" onclick="openAddMemberModal()">+ Add Member</button>
    ''' if can_manage else ''

    # Build Right Vertical Panel Dossier
    libra_dossier = f'''
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
    '''

    libra_content = f'''
    <!-- SUB-TABS & FAST ACTIONS HEADER -->
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;">
        <div class="subtabs-bar" style="margin-bottom: 0; border-bottom: none; padding-bottom: 0;">
            <button id="libra-tab-members" class="subtab-pill active" onclick="switchTab(\'members\')">👥 Members ({total_m_count}/100)</button>
            <button id="libra-tab-ranks" class="subtab-pill" onclick="switchTab(\'ranks\')">🎖️ Clan Ranks (10)</button>
            <button id="libra-tab-vehicles" class="subtab-pill" onclick="switchTab(\'vehicles\')">🚗 Fedrix Fleet ({len(vehicles)})</button>
            <button id="libra-tab-events" class="subtab-pill" onclick="switchTab(\'events\')">⚔️ Events Radar ({len(events)})</button>
            <button id="libra-tab-logs" class="subtab-pill" onclick="switchTab(\'logs\')">💰 Clan Treasury (0% Tax)</button>
        </div>
        <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="triggerRecallVehicles()">🚗 Recall Vehicles</button>
            <button class="btn btn-secondary btn-sm" onclick="triggerMeetingPoint()">📍 Meeting Point</button>
            {add_btn_html}
        </div>
    </div>

    <!-- TOP ROW: QUICK STATS -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 24px;">
        <div class="quick-stat-card" onclick="switchTab(\'members\')">
            <div class="stat-label">Fedrix Clan Roster</div>
            <div class="stat-val" style="color: #fff; font-size: 22px;">{total_m_count} <span style="font-size: 14px; color: #64748b;">/ 100</span></div>
            <div style="color: #22c55e; font-size: 12px; font-weight: 700; margin-top: 4px;">● {online_m_count} Operative Online</div>
        </div>

        <div class="quick-stat-card" onclick="switchTab(\'logs\')">
            <div class="stat-label">Clan Treasury (0% Tax)</div>
            <div class="stat-val" style="color: #22c55e; font-size: 22px;">{format_money(bal['balance'])}</div>
            <div style="color: #94a3b8; font-size: 12px; font-weight: 600; margin-top: 4px;">Direct Fedrix Clan Bank</div>
        </div>

        <div class="quick-stat-card" onclick="switchTab(\'vehicles\')">
            <div class="stat-label">Fedrix Fleet</div>
            <div class="stat-val" style="color: #fff; font-size: 22px;">{len(vehicles)} Cars</div>
            <div style="color: #c084fc; font-size: 12px; font-weight: 600; margin-top: 4px;">High-tier clan fleet</div>
        </div>

        <div class="quick-stat-card" onclick="switchTab(\'events\')">
            <div class="stat-label">Daily Events & Points</div>
            <div class="stat-val" style="color: #c084fc; font-size: 22px;">117 Pts</div>
            <div style="color: #f59e0b; font-size: 12px; font-weight: 600; margin-top: 4px;">{len(events)} Scheduled Events</div>
        </div>
    </div>

    <!-- TAB 1: MEMBERS (AUTHENTIC IN-GAME ROSTER) -->
    <div id="view-members">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;">
            <div>
                <h1 style="font-size: 26px; font-weight: 900; color: #fff; letter-spacing: -0.5px; margin: 0;">Members</h1>
                <div style="font-size: 14px; font-weight: 700; color: #94a3b8; margin-top: 4px;">{total_m_count}/100 Operatives Enrolled</div>
            </div>
            <div style="display: flex; gap: 12px; align-items: center;">
                <input type="text" class="ingame-search" id="member-search" placeholder="Search by ID or name..." onkeyup="filterMembers(this.value)" style="width:260px;">
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
                <h1 style="font-size: 26px; font-weight: 900; color: #fff; margin:0;">Clan Ranks & Hierarchy</h1>
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
                <h1 style="font-size: 26px; font-weight: 900; color: #fff; margin:0;">Fedrix Fleet ({len(vehicles)} Cars)</h1>
                <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">High-tier clan vehicles with rank requirements and insurance maintenance.</p>
            </div>
            <div style="display: flex; gap: 10px;">
                <input type="text" class="ingame-search" id="veh-search" placeholder="Search vehicle or plate..." onkeyup="filterVehicles(this.value)" style="width:240px;">
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
            <h1 style="font-size: 26px; font-weight: 900; color: #fff; margin:0;">Events Radar ({len(events)} Scheduled)</h1>
            <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">Live clan turf and combat events for Libra RP Fedrix Clan.</p>
        </div>
        <div class="grid-2">{event_cards}</div>
    </div>

    <!-- TAB 5: LOGS & TREASURY -->
    <div id="view-logs" style="display: none;">
        <div style="margin-bottom: 20px;">
            <h1 style="font-size: 26px; font-weight: 900; color: #fff; margin:0;">Clan Treasury & Transaction Logs</h1>
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
                <button class="btn btn-green" style="width:100%;" onclick="submitDeposit(\'librarp\')">Confirm Deposit</button>
            </div>

            <div class="card" style="background:#0a0c12; border: 1px solid #1a1e2b;">
                <h3 style="color:#ef4444; margin-bottom:12px;">📤 Withdraw from Libra Fund (0% Tax)</h3>
                <label style="font-size:11px; font-weight:800; color:#94a3b8;">Amount:</label>
                <input id="with-amt" type="text" placeholder="500k">
                <label style="font-size:11px; font-weight:800; color:#94a3b8;">Reason:</label>
                <input id="with-reason" type="text" placeholder="Weapons, Clan car purchase">
                <button class="btn btn-red" style="width:100%;" onclick="submitWithdraw(\'librarp\')">Confirm Withdrawal</button>
            </div>
        </div>

        <div class="card" style="padding: 0; overflow: hidden; background:#0a0c12; border: 1px solid #1a1e2b;">
            <div style="padding: 16px 20px; border-bottom: 1px solid #161924;">
                <h3 style="color:#fff; font-size:16px; margin:0;">📜 Recent Clan Transactions</h3>
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
    '''

    libra_modals = f'''
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
                <button class="btn btn-secondary" onclick="closeModal(\'rankModal\')">Cancel</button>
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
                <button class="btn btn-secondary" onclick="closeModal(\'kickModal\')">Cancel</button>
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
                <button class="btn btn-secondary" style="padding: 8px 18px;" onclick="closeModal(\'warnModal\')">Close</button>
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
                <button class="btn btn-secondary" onclick="closeModal(\'addMemberModal\')">Cancel</button>
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
                <button class="btn btn-secondary" onclick="closeModal(\'addCarModal\')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- MODAL 5: FIRST-TIME PROFILE SETUP & LINKING -->
    <div id="profileModal" class="modal-backdrop" style="{'display: flex;' if is_first_time else 'display: none;'}">
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
                <button class="btn btn-secondary" onclick="closeModal(\'dossierModal\')">Cancel</button>
            </div>
        </div>
    </div>

    <!-- TOAST BANNER -->
    <div id="toast-banner" style="display:none; position:fixed; bottom:24px; right:24px; background:#10131d; border:1.5px solid #22c55e; color:#fff; padding:14px 20px; border-radius:10px; box-shadow:0 10px 30px rgba(0,0,0,0.8); z-index:99999; font-weight:700; font-size:14px;"></div>
    '''

    libra_scripts = f'''
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
            headers: {{\'Content-Type\': \'application/json\'}},
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

        document.querySelectorAll('.subtab-pill').forEach(b => b.classList.remove('active'));
        let activeBtn = document.getElementById('libra-tab-' + tab);
        if (activeBtn) activeBtn.classList.add('active');
    }}

    // Activate initial tab from URL parameter
    switchTab('{active_tab}');

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
        if (!t) return;
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
        let el = document.getElementById(id);
        if (el) el.style.display = 'none';
    }}

    function openModal(id) {{
        let el = document.getElementById(id);
        if (el) el.style.display = 'flex';
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
                headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
            body: JSON.stringify({{ server, amount: amt, reason }})
        }});
        let d = await res.json();
        if (d.success) {{ alert("Withdrawal logged!"); location.reload(); }}
        else alert("Error: " + d.error);
    }}

    async function renewVehicle(id) {{
        let res = await fetch('/api/vehicle/renew', {{
            method: 'POST',
            headers: {{\'Content-Type\': \'application/json\'}},
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
            headers: {{\'Content-Type\': \'application/json\'}},
            body: JSON.stringify({{ identifier: id }})
        }});
        let d = await res.json();
        if (d.success) location.reload();
    }}

    async function removeEvent(id) {{
        if (!confirm("Remove event?")) return;
        let res = await fetch('/api/event/remove', {{
            method: 'POST',
            headers: {{\'Content-Type\': \'application/json\'}},
            body: JSON.stringify({{ event_id: id }})
        }});
        let d = await res.json();
        if (d.success) location.reload();
    }}
    '''

    html = render_app_shell(
        user=user,
        active_nav="libra",
        page_title="Libra RP • Fedrix Operations",
        page_subtitle="Manage Fedrix Clan Bank, 24 Vehicles, 28 Members, and Daily Events Radar",
        main_content=libra_content,
        right_rail=libra_dossier,
        extra_modals=libra_modals,
        extra_scripts=libra_scripts
    )
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

async def api_user_set_primary_persona(request: web.Request):
    user = require_user(request)
    data = await request.json()
    server = data.get("server", "grandrp")
    db.set_primary_persona(user["id"], server)
    return web.json_response({"success": True, "primary_persona": server})

async def api_activities(request: web.Request):
    server = request.query.get("server")
    limit = int(request.query.get("limit", 20))
    acts = db.get_recent_activities(limit=limit, server=server)
    return web.json_response({"success": True, "activities": acts})

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

    # REST APIs
    app.router.add_get("/api/activities", api_activities)
    app.router.add_post("/api/user/set_primary_persona", api_user_set_primary_persona)
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
