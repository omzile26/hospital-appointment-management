"""SQLite database layer for the Hospital Appointment Management System."""
import sqlite3, hashlib, os
from datetime import datetime, timedelta

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hospital.db")
STATUSES = ["Booked", "Confirmed", "In Consultation", "Completed", "Cancelled"]  # Kanban columns
PRIORITIES = ["Normal", "Urgent", "Emergency"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def hp(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def q(sql, args=(), one=False):
    """Run one SQL statement. Returns rows (or lastrowid for INSERT)."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, args)
        rows = cur.fetchall()
        c.commit()
        if sql.lstrip().upper().startswith("INSERT"):
            return cur.lastrowid
        return (rows[0] if rows else None) if one else rows
    finally:
        c.close()


def init_db():
    first = not os.path.exists(DB)
    q("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,
         username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
         role TEXT NOT NULL, full_name TEXT NOT NULL, phone TEXT)""")
    q("""CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY AUTOINCREMENT,
         user_id INTEGER, name TEXT NOT NULL, specialization TEXT)""")
    q("""CREATE TABLE IF NOT EXISTS availability(id INTEGER PRIMARY KEY AUTOINCREMENT,
         doctor_id INTEGER NOT NULL, day TEXT, start TEXT, end TEXT)""")
    q("""CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT,
         patient_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL, date TEXT, time TEXT,
         reason TEXT, priority TEXT DEFAULT 'Normal', status TEXT DEFAULT 'Booked')""")
    if first:
        seed()


def seed():
    q("INSERT INTO users(username,password,role,full_name) VALUES('admin',?,'admin','Administrator')", (hp("admin123"),))
    for i, (n, s) in enumerate([("Anita Sharma", "Cardiology"), ("Rahul Mehta", "General Physician")], 1):
        add_doctor(n, s, f"doc{i}", "doctor123")
        for d in DAYS[:5]:
            add_availability(i, d, "09:00", "13:00")
    p = register("patient1", "patient123", "Sample Patient", "9999999999")[1]
    today = datetime.now()
    for i, (st, pr) in enumerate([("Booked", "Normal"), ("Confirmed", "Urgent"), ("In Consultation", "Emergency"), ("Completed", "Normal")]):
        q("INSERT INTO appointments(patient_id,doctor_id,date,time,reason,priority,status) VALUES(?,?,?,?,?,?,?)",
          (p, 1 + i % 2, (today + timedelta(days=1)).strftime("%Y-%m-%d"), f"09:{i*30 % 60:02d}" if i < 2 else f"10:{(i-2)*30:02d}", "Check-up", pr, st))


# ---------- users ----------
def register(username, pw, name, phone):
    try:
        return True, q("INSERT INTO users(username,password,role,full_name,phone) VALUES(?,?,'patient',?,?)", (username, hp(pw), name, phone))
    except sqlite3.IntegrityError:
        return False, "Username already exists."


def login(username, pw):
    return q("SELECT * FROM users WHERE username=? AND password=?", (username, hp(pw)), True)


# ---------- doctors ----------
def add_doctor(name, spec, username, pw):
    try:
        uid = q("INSERT INTO users(username,password,role,full_name) VALUES(?,?,'doctor',?)", (username, hp(pw), name))
    except sqlite3.IntegrityError:
        return False
    q("INSERT INTO doctors(user_id,name,specialization) VALUES(?,?,?)", (uid, name, spec))
    return True


def doctors():
    return q("SELECT * FROM doctors ORDER BY name")


def doctor_of_user(uid):
    return q("SELECT * FROM doctors WHERE user_id=?", (uid,), True)


def delete_doctor(did):
    d = q("SELECT user_id FROM doctors WHERE id=?", (did,), True)
    for t in ("appointments", "availability"):
        q(f"DELETE FROM {t} WHERE doctor_id=?", (did,))
    q("DELETE FROM doctors WHERE id=?", (did,))
    if d:
        q("DELETE FROM users WHERE id=?", (d["user_id"],))


# ---------- availability ----------
def add_availability(did, day, start, end):
    q("INSERT INTO availability(doctor_id,day,start,end) VALUES(?,?,?,?)", (did, day, start, end))


def get_availability(did):
    return q("SELECT * FROM availability WHERE doctor_id=? ORDER BY start", (did,))


def delete_availability(aid):
    q("DELETE FROM availability WHERE id=?", (aid,))


def free_slots(did, date):
    d = datetime.strptime(date, "%Y-%m-%d")
    day = DAYS[d.weekday()]
    taken = {r["time"] for r in q("SELECT time FROM appointments WHERE doctor_id=? AND date=? AND status!='Cancelled'", (did, date))}
    now, out = datetime.now(), set()
    for a in q("SELECT start,end FROM availability WHERE doctor_id=? AND day=?", (did, day)):
        t, e = datetime.strptime(a["start"], "%H:%M"), datetime.strptime(a["end"], "%H:%M")
        while t < e:
            s = t.strftime("%H:%M")
            if s not in taken and not (d.date() == now.date() and s <= now.strftime("%H:%M")):
                out.add(s)
            t += timedelta(minutes=30)
    return sorted(out)


# ---------- appointments ----------
def book(patient_id, did, date, time, reason, priority):
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return False, "Date must be YYYY-MM-DD."
    if d < datetime.now().date():
        return False, "Cannot book in the past."
    if time not in free_slots(did, date):
        return False, "Selected slot is not available."
    q("INSERT INTO appointments(patient_id,doctor_id,date,time,reason,priority) VALUES(?,?,?,?,?,?)",
      (patient_id, did, date, time, reason, priority))
    return True, "Appointment booked."


def appointments(patient=None, doctor=None, search="", priority="All"):
    sql = """SELECT a.*, p.full_name patient_name, d.name doctor_name FROM appointments a
             JOIN users p ON p.id=a.patient_id JOIN doctors d ON d.id=a.doctor_id WHERE 1=1"""
    args = []
    if patient:
        sql += " AND a.patient_id=?"; args.append(patient)
    if doctor:
        sql += " AND a.doctor_id=?"; args.append(doctor)
    if search:
        sql += " AND (p.full_name LIKE ? OR d.name LIKE ? OR a.date LIKE ? OR a.reason LIKE ?)"
        args += [f"%{search}%"] * 4
    if priority != "All":
        sql += " AND a.priority=?"; args.append(priority)
    return q(sql + " ORDER BY a.date, a.time", args)


def set_status(aid, status):  # called whenever a Kanban card moves
    q("UPDATE appointments SET status=? WHERE id=?", (status, aid))


def set_priority(aid, pr):
    q("UPDATE appointments SET priority=? WHERE id=?", (pr, aid))


def get_status(aid):
    return q("SELECT status FROM appointments WHERE id=?", (aid,), True)["status"]


def stats():
    n = lambda sql: q(sql, one=True)["n"]
    return {
        "by_status": {s: q("SELECT COUNT(*) n FROM appointments WHERE status=?", (s,), True)["n"] for s in STATUSES},
        "patients": n("SELECT COUNT(*) n FROM users WHERE role='patient'"),
        "doctors": n("SELECT COUNT(*) n FROM doctors"),
        "total": n("SELECT COUNT(*) n FROM appointments"),
        "today": q("SELECT COUNT(*) n FROM appointments WHERE date=?", (datetime.now().strftime("%Y-%m-%d"),), True)["n"],
    }
