import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "thenga.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Bank Balances (GrandRP and LibraRP)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bank_balances (
        server TEXT PRIMARY KEY,
        balance REAL DEFAULT 0.0,
        total_deposited REAL DEFAULT 0.0,
        total_withdrawn REAL DEFAULT 0.0,
        total_tax_paid REAL DEFAULT 0.0
    )
    """)

    # Seed initial balances
    cursor.execute("INSERT OR IGNORE INTO bank_balances (server, balance, total_deposited, total_withdrawn, total_tax_paid) VALUES ('grandrp', 28454644.0, 0.0, 0.0, 0.0)")
    cursor.execute("INSERT OR IGNORE INTO bank_balances (server, balance, total_deposited, total_withdrawn, total_tax_paid) VALUES ('librarp', 2189500.0, 0.0, 0.0, 0.0)")

    # 2. Bank Transactions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bank_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        type TEXT NOT NULL, -- 'deposit' or 'withdraw'
        gross_amount REAL NOT NULL,
        tax_amount REAL NOT NULL,
        net_amount REAL NOT NULL,
        reason TEXT,
        proof_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 3. Family Vehicles & Insurance Expiry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server TEXT NOT NULL,
        name TEXT NOT NULL,
        plate TEXT,
        insurance_expiry TIMESTAMP,
        notes TEXT,
        added_by TEXT
    )
    """)

    # Seed initial vehicles if table is empty
    vehicle_count = cursor.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    if vehicle_count == 0:
        initial_fleet = [
            # Grand RP (EN2)
            ('grandrp', 'Coil Aleron Cabrio', '5JCS268', 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Ubermacht Arclight R', '1MIP449', 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Granger', '1ALG256', 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Buzzard (Helicopter)', None, 'Family Aircraft', 'superjedi'),
            ('grandrp', 'Truffade Éclat', 'OVER111', 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Coil Zenith Blackline', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Ubermacht Summit Signature', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Obey Sirocco V6', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Declasse Torven Cabrio', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Declasse Vigero ZX', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Obey Sirocco V6', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Declasse Aurelia Touring', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Ubermacht Apex R-Spec', '6VYI947', 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Obey Sirocco V6', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Bodhi', None, 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', None, 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', None, 'Family Truck', 'superjedi'),
            ('grandrp', 'Coil Vespera 4x4', '0JED125', 'Custom Jedi Plate', 'superjedi'),
            ('grandrp', 'Ubermacht Valora GTS', '0JED124', 'Custom Jedi Plate', 'superjedi'),
            ('grandrp', 'Annis Novus Blackline', None, 'GrandRP Garage', 'superjedi'),
            ('grandrp', 'Declasse Atlas', '0JED123', 'Custom Jedi Plate', 'superjedi'),
            ('grandrp', 'Ubermacht Revenant Touring', '0JED107', 'Custom Jedi Plate', 'superjedi'),
            ('grandrp', 'Progen Helix Roadster', '0JED100', 'Custom Jedi Plate', 'superjedi'),
            ('grandrp', 'Bodhi', '4FYR239', 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', '9QEW655', 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', '2UJU654', 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', '8KGF153', 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', '2YTH244', 'Family Truck', 'superjedi'),
            ('grandrp', 'Rebel', '8IZQ234', 'Family Truck', 'superjedi'),
            ('grandrp', 'Bodhi', '9ZIY573', 'Family Truck', 'superjedi'),
            ('grandrp', 'Rusty Rebel', '4CAG723', 'Family Truck', 'superjedi'),

            # Libra RP (Fedrix Fleet)
            ('librarp', 'Annis Elegy X50', 'FEDRIX10', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Annis R35R', 'FEDRIX11', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Benefactor Feltzer X Convertible', 'FEDRIX2', 'Rank 4+ Required', 'superjedi'),
            ('librarp', 'Benefactor GT Black Series', 'FEDRIX9', 'Rank 4+ Required', 'superjedi'),
            ('librarp', 'Benefactor GX63', 'FEDRIX15', 'Rank 2+ Required', 'superjedi'),
            ('librarp', 'Benefactor X223', 'FEDRIX3', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Bravado Bison 1500', 'FEDRIX8', 'Rank 2+ Required', 'superjedi'),
            ('librarp', 'Bravado Bison TX', 'FEDRIX6', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Coil Raiden Cross', None, 'Rank 1+ (No Plate)', 'superjedi'),
            ('librarp', 'Coil Tempest', 'FEDRIX16', 'Rank 1+ Required', 'superjedi'),
            ('librarp', 'Declasse C7', 'JOKBR', 'Rank 1+ Required', 'superjedi'),
            ('librarp', 'Emperor Cruise 300', 'FEDRIX14', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Emperor LF', 'FEDRIX5', 'Rank 2+ Required', 'superjedi'),
            ('librarp', 'Gallivanter Baller SVX', None, 'Rank 1+ (No Plate)', 'superjedi'),
            ('librarp', 'Karin L500', 'FEDRIX', 'Rank 3+ Required', 'superjedi'),
            ('librarp', 'Karin L500', 'FEDR1X', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Karin WRX', None, 'Rank 1+ (No Plate)', 'superjedi'),
            ('librarp', 'Maibatsu Frogger', None, 'Rank 6+ Helicopter (No Plate)', 'superjedi'),
            ('librarp', 'Overflod Zenith GT', 'FEDRIX13', 'Rank 5+ Required', 'superjedi'),
            ('librarp', 'Pegassi Terzo', 'FEDRIX12', 'Rank 4+ Required', 'superjedi'),
            ('librarp', 'Pegassi Ursano', 'FEDRIX7', 'Rank 6+ Required', 'superjedi'),
            ('librarp', 'Pfister GT-One', 'J8KER', 'Rank 5+ Required', 'superjedi'),
            ('librarp', 'Rebel', 'JOK3R', 'Rank 1+ Required', 'superjedi'),
            ('librarp', 'Ubermacht M5 DRIFT', 'FEDRIX4', 'Rank 9+ Required', 'superjedi')
        ]
        cursor.executemany("""
        INSERT INTO vehicles (server, name, plate, insurance_expiry, notes, added_by)
        VALUES (?, ?, ?, NULL, ?, ?)
        """, initial_fleet)

    # Auto-migration for vehicles table (image_url)
    cursor.execute("PRAGMA table_info(vehicles)")
    veh_cols = [c[1] for c in cursor.fetchall()]
    if "image_url" not in veh_cols:
        cursor.execute("ALTER TABLE vehicles ADD COLUMN image_url TEXT")

    # Update Grand RP vehicle image URLs for IDs 1..31
    for vid in range(1, 32):
        cursor.execute(
            "UPDATE vehicles SET image_url = ? WHERE id = ? AND server = 'grandrp' AND (image_url IS NULL OR image_url = '')",
            (f"/static/vehicles/grand_veh_{vid}.png", vid)
        )

    # 4. Plantation (GrandRP Pineapple)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plantation (
        id INTEGER PRIMARY KEY,
        server TEXT DEFAULT 'grandrp',
        crop TEXT DEFAULT 'Pineapple',
        status TEXT DEFAULT 'IDLE', -- 'GROWING', 'READY', 'IDLE'
        planted_at TIMESTAMP,
        last_nourished_at TIMESTAMP,
        next_nourish_due TIMESTAMP,
        harvest_due TIMESTAMP,
        alert_channel_id INTEGER,
        last_notified_nourish INTEGER DEFAULT 0,
        last_notified_harvest INTEGER DEFAULT 0
    )
    """)
    cursor.execute("INSERT OR IGNORE INTO plantation (id, server, crop, status) VALUES (1, 'grandrp', 'Pineapple', 'IDLE')")

    # 5. Event Alert System (LibraRP)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server TEXT DEFAULT 'librarp',
        name TEXT NOT NULL,
        time_utc TEXT NOT NULL,
        description TEXT,
        role_id INTEGER,
        channel_id INTEGER,
        frequency TEXT DEFAULT 'Daily',
        last_triggered_date TEXT DEFAULT ''
    )
    """)

    event_count = cursor.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if event_count == 0:
        cursor.execute("""
        INSERT INTO events (server, name, time_utc, description, role_id, channel_id)
        VALUES ('librarp', 'Crown Holder', '10:00', 'Location: Grand Senora Desert (Radius: 120m) • Duration: 15m (Join window: 5m) [05:00 ET]', NULL, 0)
        """)
        cursor.execute("""
        INSERT INTO events (server, name, time_utc, description, role_id, channel_id)
        VALUES ('librarp', 'Weapon Factory', '13:00', 'Location: Paleto Bay Weapon Factory (Radius: 125m) • Rewards: Weapons, Ammo, Armor, Clan Points [08:00 ET]', NULL, 0)
        """)
        cursor.execute("""
        INSERT INTO events (server, name, time_utc, description, role_id, channel_id)
        VALUES ('librarp', 'Cartel War', '02:30', 'Location: #17 Grand Senora Desert (Radius: 150m) • Daily Limit: 3/24 [21:30 ET]', NULL, 0)
        """)

    # 5. User Profiles (GrandRP and LibraRP Ranks)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        grand_rank TEXT DEFAULT 'Member (Rank 1)',
        libra_rank TEXT DEFAULT 'Associate (Rank 1)',
        libra_member_id INTEGER,
        grand_member_name TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # Auto-migration for existing user_profiles tables
    cursor.execute("PRAGMA table_info(user_profiles)")
    cols = [c[1] for c in cursor.fetchall()]
    if "libra_member_id" not in cols:
        cursor.execute("ALTER TABLE user_profiles ADD COLUMN libra_member_id INTEGER")
    if "grand_member_name" not in cols:
        cursor.execute("ALTER TABLE user_profiles ADD COLUMN grand_member_name TEXT")
    if "profile_completed" not in cols:
        cursor.execute("ALTER TABLE user_profiles ADD COLUMN profile_completed INTEGER DEFAULT 0")
        cursor.execute("UPDATE user_profiles SET profile_completed = 1 WHERE libra_member_id IS NOT NULL OR grand_member_name IS NOT NULL OR username LIKE '%superjedi%'")
    
    dossier_cols = [
        ("grand_member_id", "TEXT DEFAULT '7104'"),
        ("grand_recent_activity", "TEXT DEFAULT 'Pineapple Plantation Harvest Banked • Active Fleet Operative'"),
        ("grand_awards", "TEXT DEFAULT ''"),
        ("grand_punishments", "TEXT DEFAULT 'Clean Record (0 Active Warnings)'"),
        ("libra_recent_activity", "TEXT DEFAULT '● Online now • Fedrix Clan Operations'"),
        ("libra_awards", "TEXT DEFAULT ''"),
        ("libra_punishments", "TEXT DEFAULT 'Good Standing (0 Suspensions)'"),
        ("discord_rank", "TEXT DEFAULT '👑 High Command Staff'"),
        ("discord_recent_activity", "TEXT DEFAULT 'Authenticated via OAuth2 • Command Center Active'"),
        ("discord_awards", "TEXT DEFAULT ''"),
        ("discord_punishments", "TEXT DEFAULT 'Clean Record (0 Mutes / Warnings)'"),
        ("primary_persona", "TEXT DEFAULT 'grandrp'")
    ]
    for c_name, c_def in dossier_cols:
        if c_name not in cols:
            try:
                cursor.execute(f"ALTER TABLE user_profiles ADD COLUMN {c_name} {c_def}")
            except Exception:
                pass

    # Clear any placeholder awards so it stays empty until awarded by leadership
    try:
        cursor.execute("UPDATE user_profiles SET grand_awards = '' WHERE grand_awards LIKE '%Malayali Club Honor Medal%'")
        cursor.execute("UPDATE user_profiles SET libra_awards = '' WHERE libra_awards LIKE '%Fedrix Vanguard Cross%'")
        cursor.execute("UPDATE user_profiles SET discord_awards = '' WHERE discord_awards LIKE '%Server Creator%'")
    except Exception:
        pass

    # 6. Libra RP Ranks Hierarchy
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libra_ranks (
        level INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        can_manage BOOLEAN DEFAULT 0
    )
    """)
    rank_count = cursor.execute("SELECT COUNT(*) FROM libra_ranks").fetchone()[0]
    if rank_count == 0:
        cursor.executemany("INSERT INTO libra_ranks (level, name, can_manage) VALUES (?, ?, ?)", [
            (1, 'Leader', 1),
            (2, 'Co-Leader', 1),
            (3, 'Supervisor', 1),
            (4, 'Enforcer', 0),
            (5, 'Pro', 0),
            (6, 'Ranger', 0),
            (7, 'Trainee', 0),
            (8, 'SUSPENDED', 0),
            (9, 'VAAZHA', 0),
            (11, 'GUEST', 0)
        ])

    # 7. Libra RP Clan Members (Fedrix Roster - 28 Members)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libra_members (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        rank_level INTEGER NOT NULL,
        rank_name TEXT NOT NULL,
        last_seen TEXT,
        is_online BOOLEAN DEFAULT 0,
        discord_id TEXT,
        discord_username TEXT
    )
    """)
    # Auto-migration for existing libra_members tables
    cursor.execute("PRAGMA table_info(libra_members)")
    l_cols = [c[1] for c in cursor.fetchall()]
    if "discord_id" not in l_cols:
        cursor.execute("ALTER TABLE libra_members ADD COLUMN discord_id TEXT")
    if "discord_username" not in l_cols:
        cursor.execute("ALTER TABLE libra_members ADD COLUMN discord_username TEXT")
    if "warnings" not in l_cols:
        cursor.execute("ALTER TABLE libra_members ADD COLUMN warnings INTEGER DEFAULT 0")

    # 8. Libra RP Clan Warnings (Isolated from Grand & Discord)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libra_warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        member_name TEXT NOT NULL,
        reason TEXT NOT NULL,
        issued_by TEXT NOT NULL,
        strike_number INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
    )
    """)
    member_count = cursor.execute("SELECT COUNT(*) FROM libra_members").fetchone()[0]
    if member_count == 0:
        initial_members = [
            (5392, 'Superjedi Tnga', 2, 'Co-Leader', 'Online now', 1, None, None),
            (5665, 'Joker Fedrix', 1, 'Leader', '11/10/2026, 11:06:00', 0, None, None),
            (6377, 'Body Bagger', 2, 'Co-Leader', '11/10/2026, 16:53:48', 0, None, None),
            (5921, 'Raik Andreev', 2, 'Co-Leader', '11/10/2026, 11:05:12', 0, None, None),
            (6178, 'Kutteppan Jose', 3, 'Supervisor', '11/10/2026, 13:58:01', 0, None, None),
            (6301, 'Leo Depaul', 3, 'Supervisor', '11/10/2026, 11:07:37', 0, None, None),
            (6192, 'Cameo Namboothiri', 4, 'Enforcer', '11/05/2026, 04:19:52', 0, None, None),
            (6139, 'Fedrix Klaus', 4, 'Enforcer', '10/31/2026, 12:10:50', 0, None, None),
            (5767, 'George Kutty', 4, 'Enforcer', '11/10/2026, 11:05:48', 0, None, None),
            (6311, 'John Honai', 4, 'Enforcer', '11/08/2026, 07:13:03', 0, None, None),
            (207, 'Kraken Valerio', 4, 'Enforcer', '11/10/2026, 21:17:03', 0, None, None),
            (5740, 'Magudi Das', 4, 'Enforcer', '10/25/2026, 01:41:59', 0, None, None),
            (5971, 'Rocky Wlxxx', 4, 'Enforcer', '11/10/2026, 12:21:53', 0, None, None),
            (5701, 'Tom Mathew', 4, 'Enforcer', '11/10/2026, 11:06:16', 0, None, None),
            (7340, 'Alish Yadav', 5, 'Pro', '10/22/2026, 08:33:23', 0, None, None),
            (5748, 'Dragon Palley', 5, 'Pro', '11/02/2026, 07:35:09', 0, None, None),
            (7873, 'Hugh Logan', 5, 'Pro', '10/19/2026, 12:25:47', 0, None, None),
            (5732, 'Hydhros Alibay', 5, 'Pro', '11/09/2026, 18:20:00', 0, None, None),
            (5988, 'Mgc Abu', 5, 'Pro', '11/08/2026, 20:15:00', 0, None, None),
            (6436, 'Reacher Blake', 5, 'Pro', '11/07/2026, 14:10:00', 0, None, None),
            (5797, 'Speedy White', 5, 'Pro', '11/09/2026, 22:45:00', 0, None, None),
            (8017, 'Starkz Boy', 5, 'Pro', '11/06/2026, 16:30:00', 0, None, None),
            (7583, 'Sukumara Kurup', 5, 'Pro', '11/10/2026, 19:05:00', 0, None, None),
            (5807, 'Kakarot Gaming', 6, 'Ranger', '11/05/2026, 11:00:00', 0, None, None),
            (10896, 'Karma Nyx', 6, 'Ranger', '11/04/2026, 13:22:00', 0, None, None),
            (8131, 'Kassia Valenti', 6, 'Ranger', '11/03/2026, 15:40:00', 0, None, None),
            (10617, 'Veek Sticky', 6, 'Ranger', '11/08/2026, 17:50:00', 0, None, None),
            (11024, 'Rsz Steve', 11, 'GUEST', '11/01/2026, 09:12:00', 0, None, None)
        ]
        cursor.executemany("""
        INSERT INTO libra_members (id, name, rank_level, rank_name, last_seen, is_online, discord_id, discord_username)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, initial_members)

    # 9. App Settings (Persistent Server Configuration & Secret Keys)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 10. Persistent User Sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        session_token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        avatar_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    )
    """)

    # 11. Network Live Activities (Operations Hub Feed)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS network_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        actor TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    act_count = cursor.execute("SELECT COUNT(*) FROM network_activities").fetchone()[0]
    if act_count == 0:
        cursor.executemany("""
        INSERT INTO network_activities (server, category, title, description, actor, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, [
            ('grandrp', 'treasury', 'Treasury updated', 'Grand RP • EN2 — +$120,000 (property sale)', 'superjedi', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ('librarp', 'fleet', 'Fleet change', 'Libra RP • Fedrix — +1 vehicle (Patrol)', 'superjedi', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ('grandrp', 'events', 'Event published', 'Grand RP • EN2 — Community Meet (Feb 2)', 'superjedi', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ('librarp', 'persona', 'Persona linked', 'Superjedi Tnga → Libra RP • Fedrix', 'superjedi', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ])

    conn.commit()
    conn.close()

# ==================== BANK FUNCTIONS ====================

def get_bank_balance(server: str) -> Dict[str, Any]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM bank_balances WHERE server = ?", (server.lower(),)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"server": server.lower(), "balance": 0.0, "total_deposited": 0.0, "total_withdrawn": 0.0, "total_tax_paid": 0.0}

def set_bank_balance(server: str, new_balance: float):
    conn = get_connection()
    conn.execute("UPDATE bank_balances SET balance = ? WHERE server = ?", (new_balance, server.lower()))
    conn.commit()
    conn.close()

def record_bank_transaction(server: str, user_id: int, user_name: str, tx_type: str, gross: float, tax: float, net: float, reason: str, proof_url: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO bank_transactions (server, user_id, user_name, type, gross_amount, tax_amount, net_amount, reason, proof_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (server.lower(), user_id, user_name, tx_type, gross, tax, net, reason, proof_url))

    if tx_type == "deposit":
        cursor.execute("""
        UPDATE bank_balances
        SET balance = balance + ?,
            total_deposited = total_deposited + ?,
            total_tax_paid = total_tax_paid + ?
        WHERE server = ?
        """, (net, gross, tax, server.lower()))
    elif tx_type == "withdraw":
        cursor.execute("""
        UPDATE bank_balances
        SET balance = balance - ?,
            total_withdrawn = total_withdrawn + ?,
            total_tax_paid = total_tax_paid + ?
        WHERE server = ?
        """, (gross, gross, tax, server.lower()))

    conn.commit()
    conn.close()

    srv_name = "Grand RP • EN2" if "grand" in server.lower() else "Libra RP • Fedrix"
    sign = "+" if tx_type == "deposit" else "-"
    log_activity(
        server=server,
        category="treasury",
        title="Treasury updated",
        description=f"{srv_name} — {sign}${net:,.0f} ({reason or 'Operations'})",
        actor=user_name
    )

def get_recent_transactions(server: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
    SELECT * FROM bank_transactions WHERE server = ? ORDER BY id DESC LIMIT ?
    """, (server.lower(), limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ==================== VEHICLE FUNCTIONS ====================

def add_vehicle(server: str, name: str, plate: Optional[str], expiry_dt: Optional[datetime], notes: str, added_by: str, image_url: Optional[str] = None):
    conn = get_connection()
    expiry_str = expiry_dt.isoformat() if expiry_dt else None
    clean_plate = plate.strip().upper() if plate else None
    conn.execute("""
    INSERT INTO vehicles (server, name, plate, insurance_expiry, notes, added_by, image_url)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (server.lower(), name, clean_plate, expiry_str, notes, added_by, image_url))
    conn.commit()
    conn.close()

    srv_name = "Grand RP • EN2" if "grand" in server.lower() else "Libra RP • Fedrix"
    log_activity(
        server=server,
        category="fleet",
        title="Fleet change",
        description=f"{srv_name} — +1 vehicle ({name})",
        actor=added_by
    )

def get_vehicles(server: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if server:
        rows = conn.execute("SELECT * FROM vehicles WHERE server = ? ORDER BY id ASC", (server.lower(),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM vehicles ORDER BY server ASC, id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def renew_vehicle_insurance(identifier: str, new_expiry_dt: datetime) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    clean_id = str(identifier).strip().upper()

    if clean_id.isdigit():
        cursor.execute("UPDATE vehicles SET insurance_expiry = ? WHERE id = ?", (new_expiry_dt.isoformat(), int(clean_id)))
    else:
        cursor.execute("UPDATE vehicles SET insurance_expiry = ? WHERE plate = ?", (new_expiry_dt.isoformat(), clean_id))

    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def remove_vehicle(identifier: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    clean_id = str(identifier).strip().upper()

    if clean_id.isdigit():
        cursor.execute("DELETE FROM vehicles WHERE id = ?", (int(clean_id),))
    else:
        cursor.execute("DELETE FROM vehicles WHERE plate = ?", (clean_id,))

    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# ==================== PLANTATION FUNCTIONS (GRAND RP) ====================

def get_plantation_state() -> Dict[str, Any]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM plantation WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else {}

def set_plantation_planted(planted_at: datetime, next_nourish: datetime, harvest_due: datetime, channel_id: int):
    conn = get_connection()
    conn.execute("""
    UPDATE plantation SET
        status = 'GROWING',
        crop = 'Pineapple',
        planted_at = ?,
        last_nourished_at = ?,
        next_nourish_due = ?,
        harvest_due = ?,
        alert_channel_id = ?,
        last_notified_nourish = 0,
        last_notified_harvest = 0
    WHERE id = 1
    """, (planted_at.isoformat(), planted_at.isoformat(), next_nourish.isoformat(), harvest_due.isoformat(), channel_id))
    conn.commit()
    conn.close()

def update_plantation_nourish(nourished_at: datetime, next_nourish: datetime):
    conn = get_connection()
    conn.execute("""
    UPDATE plantation SET
        last_nourished_at = ?,
        next_nourish_due = ?,
        last_notified_nourish = 0
    WHERE id = 1
    """, (nourished_at.isoformat(), next_nourish.isoformat()))
    conn.commit()
    conn.close()

def reset_plantation():
    conn = get_connection()
    conn.execute("""
    UPDATE plantation SET
        status = 'IDLE',
        planted_at = NULL,
        last_nourished_at = NULL,
        next_nourish_due = NULL,
        harvest_due = NULL,
        last_notified_nourish = 0,
        last_notified_harvest = 0
    WHERE id = 1
    """)
    conn.commit()
    conn.close()

def mark_plantation_notified(field: str):
    conn = get_connection()
    conn.execute(f"UPDATE plantation SET {field} = 1 WHERE id = 1")
    conn.commit()
    conn.close()

# ==================== EVENT FUNCTIONS (LIBRA RP) ====================

def add_event(server: str, name: str, time_utc: str, description: str, role_id: Optional[int], channel_id: int):
    conn = get_connection()
    conn.execute("""
    INSERT INTO events (server, name, time_utc, description, role_id, channel_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (server.lower(), name, time_utc.strip(), description, role_id, channel_id))
    conn.commit()
    conn.close()

def get_events(server: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if server:
        rows = conn.execute("SELECT * FROM events WHERE server = ? ORDER BY time_utc ASC", (server.lower(),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM events ORDER BY server ASC, time_utc ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def remove_event(event_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# ==================== USER PROFILE & RANKS ====================

def get_user_profile(user_id: str, username: str = "Member") -> Dict[str, Any]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (str(user_id),)).fetchone()
    is_founder = "superjedi" in username.lower()
    
    if not row:
        default_grand = "Leader / High Command (Rank 10)" if is_founder else "Family Member (Rank 1)"
        default_libra = "Lv 2 Co-Leader" if is_founder else "Fedrix Associate (Rank 1)"
        libra_id = 5392 if is_founder else None
        completed = 1 if is_founder else 0
        conn.execute("""
        INSERT OR IGNORE INTO user_profiles (user_id, username, grand_rank, libra_rank, libra_member_id, grand_member_name, profile_completed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(user_id), username, default_grand, default_libra, libra_id, "Superjedi Tnga" if is_founder else username, completed))
        conn.commit()
        row = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (str(user_id),)).fetchone()

    if is_founder:
        conn.execute("""
        UPDATE libra_members
        SET discord_id = ?, discord_username = ?
        WHERE id = 5392 AND (discord_id IS NULL OR discord_id != ?)
        """, (str(user_id), username, str(user_id)))
        conn.commit()

    conn.close()
    return dict(row)

def update_user_ranks(user_id: str, grand_rank: str, libra_rank: str) -> bool:
    conn = get_connection()
    conn.execute("""
    UPDATE user_profiles
    SET grand_rank = ?, libra_rank = ?, updated_at = CURRENT_TIMESTAMP
    WHERE user_id = ?
    """, (grand_rank.strip(), libra_rank.strip(), str(user_id)))
    conn.commit()
    conn.close()
    return True

def update_user_dossier(user_id: str, dossier_data: dict) -> bool:
    conn = get_connection()
    allowed_keys = [
        "grand_member_name", "grand_member_id", "grand_rank", "grand_recent_activity", "grand_awards", "grand_punishments",
        "libra_recent_activity", "libra_awards", "libra_punishments",
        "discord_rank", "discord_recent_activity", "discord_awards", "discord_punishments"
    ]
    set_clauses = []
    values = []
    for k, v in dossier_data.items():
        if k in allowed_keys:
            set_clauses.append(f"{k} = ?")
            values.append(str(v).strip())
    
    if set_clauses:
        values.append(str(user_id))
        query = f"UPDATE user_profiles SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?"
        conn.execute(query, values)
        conn.commit()
    conn.close()
    return True

# ==================== LIBRA FEDRIX ROSTER & MANAGEMENT ====================

def get_libra_members() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM libra_members ORDER BY rank_level ASC, name ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_libra_ranks() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM libra_ranks ORDER BY level ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_libra_member_by_discord(discord_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM libra_members WHERE discord_id = ?", (str(discord_id),)).fetchone()
    conn.close()
    return dict(row) if row else None

def link_libra_member(member_id: int, discord_id: str, discord_username: str) -> bool:
    conn = get_connection()
    conn.execute("UPDATE libra_members SET discord_id = NULL, discord_username = NULL WHERE discord_id = ?", (str(discord_id),))
    conn.execute("""
    UPDATE libra_members
    SET discord_id = ?, discord_username = ?
    WHERE id = ?
    """, (str(discord_id), discord_username, int(member_id)))
    m = conn.execute("SELECT * FROM libra_members WHERE id = ?", (int(member_id),)).fetchone()
    if m:
        rank_str = f"Lv {m['rank_level']} {m['rank_name']}"
        conn.execute("""
        UPDATE user_profiles
        SET libra_rank = ?, libra_member_id = ?, username = ?
        WHERE user_id = ?
        """, (rank_str, int(member_id), discord_username, str(discord_id)))
    conn.commit()
    conn.close()
    return True

def link_user_profiles(user_id: str, username: str, libra_member_id: Optional[int], grand_name: str, grand_rank: str) -> bool:
    conn = get_connection()
    libra_rank_str = "Associate (Rank 1)"
    if libra_member_id:
        conn.execute("UPDATE libra_members SET discord_id = NULL, discord_username = NULL WHERE discord_id = ?", (str(user_id),))
        conn.execute("""
        UPDATE libra_members
        SET discord_id = ?, discord_username = ?
        WHERE id = ?
        """, (str(user_id), username, int(libra_member_id)))
        m = conn.execute("SELECT * FROM libra_members WHERE id = ?", (int(libra_member_id),)).fetchone()
        if m:
            libra_rank_str = f"Lv {m['rank_level']} {m['rank_name']}"

    conn.execute("""
    INSERT INTO user_profiles (user_id, username, grand_rank, libra_rank, libra_member_id, grand_member_name, profile_completed, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id) DO UPDATE SET
        username = excluded.username,
        grand_rank = excluded.grand_rank,
        libra_rank = excluded.libra_rank,
        libra_member_id = excluded.libra_member_id,
        grand_member_name = excluded.grand_member_name,
        profile_completed = 1,
        updated_at = CURRENT_TIMESTAMP
    """, (str(user_id), username, grand_rank, libra_rank_str, libra_member_id, grand_name))

    conn.commit()
    conn.close()
    return True

def dismiss_user_profile_prompt(user_id: str) -> bool:
    conn = get_connection()
    conn.execute("""
    INSERT INTO user_profiles (user_id, username, profile_completed, updated_at)
    VALUES (?, 'Operative', 1, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id) DO UPDATE SET profile_completed = 1, updated_at = CURRENT_TIMESTAMP
    """, (str(user_id),))
    conn.commit()
    conn.close()
    return True

def add_libra_member(member_id: int, name: str, rank_level: int, rank_name: str, last_seen: str = "Just joined") -> bool:
    conn = get_connection()
    conn.execute("""
    INSERT OR REPLACE INTO libra_members (id, name, rank_level, rank_name, last_seen, is_online, discord_id, discord_username)
    VALUES (?, ?, ?, ?, ?, 0, NULL, NULL)
    """, (int(member_id), name.strip(), int(rank_level), rank_name.strip(), last_seen))
    conn.commit()
    conn.close()
    return True

def update_libra_member_rank(member_id: int, new_level: int, new_rank_name: str) -> bool:
    conn = get_connection()
    conn.execute("""
    UPDATE libra_members
    SET rank_level = ?, rank_name = ?
    WHERE id = ?
    """, (int(new_level), new_rank_name, int(member_id)))
    m = conn.execute("SELECT * FROM libra_members WHERE id = ?", (int(member_id),)).fetchone()
    if m and m['discord_id']:
        rank_str = f"Lv {new_level} {new_rank_name}"
        conn.execute("UPDATE user_profiles SET libra_rank = ? WHERE user_id = ?", (rank_str, str(m['discord_id'])))
    conn.commit()
    conn.close()
    return True

def kick_libra_member(member_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM libra_members WHERE id = ?", (int(member_id),))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def user_can_manage_libra(user: dict, target_level: Optional[int] = None) -> bool:
    """
    Returns True if user has permission to manage Libra clan members.
    If target_level is specified, enforces that user's rank is strictly higher
    (lower number) than the target, except Founder/Admin who can manage any rank.
    """
    if not user:
        return False
    from utils import is_admin_user
    if is_admin_user(user):
        return True
    
    conn = get_connection()
    row = conn.execute("SELECT rank_level FROM libra_members WHERE discord_id = ?", (str(user.get("id")),)).fetchone()
    conn.close()
    if not row:
        return False
    
    actor_level = row['rank_level']
    if actor_level not in [1, 2, 3]:
        return False
    
    if target_level is not None:
        # Strictly higher rank (e.g. Lv 1 Leader can manage Lv 2+, Lv 2 Co-Leader can manage Lv 3+, Lv 3 Supervisor can manage Lv 4+)
        return actor_level < target_level
    
    return True

# ==================== LIBRA WARNINGS SYSTEM ====================

def get_libra_warnings(member_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if member_id:
        rows = conn.execute("SELECT * FROM libra_warnings WHERE member_id = ? AND is_active = 1 ORDER BY created_at DESC", (int(member_id),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM libra_warnings ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_libra_warning(member_id: int, reason: str, issued_by: str) -> Dict[str, Any]:
    conn = get_connection()
    m = conn.execute("SELECT name, warnings, rank_level FROM libra_members WHERE id = ?", (int(member_id),)).fetchone()
    if not m:
        conn.close()
        return {"success": False, "error": "Member not found"}
    
    cur_warnings = m['warnings'] or 0
    new_count = cur_warnings + 1
    
    conn.execute("UPDATE libra_members SET warnings = ? WHERE id = ?", (new_count, int(member_id)))
    conn.execute("""
    INSERT INTO libra_warnings (member_id, member_name, reason, issued_by, strike_number, is_active)
    VALUES (?, ?, ?, ?, ?, 1)
    """, (int(member_id), m['name'], reason.strip(), issued_by.strip(), new_count))
    
    # Update linked user profile disciplinary status
    m_row = conn.execute("SELECT discord_id FROM libra_members WHERE id = ?", (int(member_id),)).fetchone()
    if m_row and m_row['discord_id']:
        conn.execute("""
        UPDATE user_profiles
        SET libra_punishments = ?
        WHERE user_id = ?
        """, (f"⚠️ {new_count}/3 Warnings: {reason.strip()}", str(m_row['discord_id'])))
    
    conn.commit()
    conn.close()
    return {
        "success": True,
        "member_id": int(member_id),
        "member_name": m['name'],
        "strike_number": new_count,
        "reason": reason.strip(),
        "issued_by": issued_by.strip()
    }

def clear_libra_warnings(member_id: int) -> bool:
    conn = get_connection()
    conn.execute("UPDATE libra_members SET warnings = 0 WHERE id = ?", (int(member_id),))
    conn.execute("UPDATE libra_warnings SET is_active = 0 WHERE member_id = ?", (int(member_id),))
    
    m_row = conn.execute("SELECT discord_id FROM libra_members WHERE id = ?", (int(member_id),)).fetchone()
    if m_row and m_row['discord_id']:
        conn.execute("""
        UPDATE user_profiles
        SET libra_punishments = 'Good Standing (0 Suspensions)'
        WHERE user_id = ?
        """, (str(m_row['discord_id']),))
        
    conn.commit()
    conn.close()
    return True

# ==================== APP SETTINGS & SESSION SECRET ====================

def get_app_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_app_setting(key: str, value: str):
    conn = get_connection()
    conn.execute("""
    INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    """, (key, str(value)))
    conn.commit()
    conn.close()

def get_or_create_session_secret() -> str:
    # 1. Environment variable if explicitly set
    env_sec = os.getenv("SESSION_SECRET")
    if env_sec and len(env_sec.strip()) >= 16:
        return env_sec.strip()

    # 2. Database persistent setting
    existing = get_app_setting("session_secret")
    if existing and len(existing) >= 16:
        return existing

    # 3. Generate a permanent cryptographically strong key and persist in database
    import secrets
    new_secret = secrets.token_hex(32)
    set_app_setting("session_secret", new_secret)
    return new_secret

# ==================== USER SESSIONS ====================

def save_user_session(token: str, user_id: str, username: str, avatar_url: Optional[str] = None, days: int = 90):
    from datetime import datetime, timedelta
    expires = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    conn.execute("""
    INSERT INTO user_sessions (session_token, user_id, username, avatar_url, expires_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(session_token) DO UPDATE SET
        user_id = excluded.user_id,
        username = excluded.username,
        avatar_url = excluded.avatar_url,
        expires_at = excluded.expires_at
    """, (token, str(user_id), username, avatar_url or "", expires))
    conn.commit()
    conn.close()

def get_user_session(token: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("""
    SELECT user_id, username, avatar_url, expires_at
    FROM user_sessions
    WHERE session_token = ? AND expires_at > datetime('now')
    """, (token,)).fetchone()
    conn.close()
    if row:
        return {
            "id": row['user_id'],
            "username": row['username'],
            "avatar_url": row['avatar_url']
        }
    return None

def delete_user_session(token: str):
    conn = get_connection()
    conn.execute("DELETE FROM user_sessions WHERE session_token = ?", (token,))
    conn.commit()
    conn.close()

def set_primary_persona(user_id: str, server: str) -> bool:
    clean_server = 'librarp' if 'libra' in server.lower() else 'grandrp'
    conn = get_connection()
    conn.execute("UPDATE user_profiles SET primary_persona = ? WHERE user_id = ?", (clean_server, str(user_id)))
    conn.commit()
    conn.close()
    return True

# ==================== ACTIVITIES SYSTEM ====================

def log_activity(server: str, category: str, title: str, description: str, actor: Optional[str] = None):
    try:
        conn = get_connection()
        conn.execute("""
        INSERT INTO network_activities (server, category, title, description, actor)
        VALUES (?, ?, ?, ?, ?)
        """, (server.lower(), category.lower(), title.strip(), description.strip(), actor or 'System'))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging activity: {e}")

def get_recent_activities(limit: int = 10, server: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if server:
        rows = conn.execute("""
        SELECT * FROM network_activities WHERE server = ? ORDER BY id DESC LIMIT ?
        """, (server.lower(), limit)).fetchall()
    else:
        rows = conn.execute("""
        SELECT * FROM network_activities ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Initialize database tables on load
init_db()
