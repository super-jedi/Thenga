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

def get_recent_transactions(server: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
    SELECT * FROM bank_transactions WHERE server = ? ORDER BY id DESC LIMIT ?
    """, (server.lower(), limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ==================== VEHICLE FUNCTIONS ====================

def add_vehicle(server: str, name: str, plate: Optional[str], expiry_dt: Optional[datetime], notes: str, added_by: str):
    conn = get_connection()
    expiry_str = expiry_dt.isoformat() if expiry_dt else None
    clean_plate = plate.strip().upper() if plate else None
    conn.execute("""
    INSERT INTO vehicles (server, name, plate, insurance_expiry, notes, added_by)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (server.lower(), name, clean_plate, expiry_str, notes, added_by))
    conn.commit()
    conn.close()

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

# Initialize database tables on load
init_db()
