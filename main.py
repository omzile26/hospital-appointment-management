"""Hospital Appointment Management System - run with: python main.py"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
import database as db
from kanban import KanbanBoard


def pid(text):
    return int(text.split(" - ")[0])


def doctor_choices():
    return [f"{d['id']} - {d['name']} ({d['specialization']})" for d in db.doctors()]


def make_tree(parent, cols, height=12):
    t = ttk.Treeview(parent, columns=cols, show="headings", height=height)
    for c in cols:
        t.heading(c, text=c.title()); t.column(c, width=110, anchor="center")
    t.pack(fill="both", expand=True, padx=10, pady=6)
    return t


class AppointmentTable(ttk.Frame):
    """Appointment history with search. Patients can cancel from here."""
    def __init__(self, parent, patient=None, doctor=None, cancel=False):
        super().__init__(parent)
        self.patient, self.doctor = patient, doctor
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=6)
        self.q = tk.StringVar()
        ttk.Label(top, text="Search:").pack(side="left")
        e = ttk.Entry(top, textvariable=self.q, width=28); e.pack(side="left", padx=5)
        e.bind("<KeyRelease>", lambda _: self.refresh())
        if cancel:
            ttk.Button(top, text="Cancel Selected Appointment", command=self.cancel).pack(side="right")
        self.tree = make_tree(self, ("id", "patient", "doctor", "date", "time", "priority", "status", "reason"))
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for r in db.appointments(self.patient, self.doctor, self.q.get().strip()):
            self.tree.insert("", "end", values=(r["id"], r["patient_name"], r["doctor_name"], r["date"],
                                                r["time"], r["priority"], r["status"], r["reason"]))

    def cancel(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showinfo("Cancel", "Select an appointment first.")
        v = self.tree.item(sel[0])["values"]
        if v[6] not in ("Booked", "Confirmed"):
            return messagebox.showwarning("Cancel", f"A '{v[6]}' appointment cannot be cancelled.")
        if messagebox.askyesno("Cancel", f"Cancel appointment #{v[0]}?"):
            db.set_status(v[0], "Cancelled")
            self.refresh()


class Dashboard(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.box = ttk.Frame(self); self.box.pack(padx=20, pady=20, anchor="w")
        self.refresh()

    def refresh(self):
        for w in self.box.winfo_children():
            w.destroy()
        s = db.stats()
        items = [("Patients", s["patients"]), ("Doctors", s["doctors"]), ("Total Appointments", s["total"]),
                 ("Today's Appointments", s["today"])] + list(s["by_status"].items())
        for i, (k, v) in enumerate(items):
            c = tk.Frame(self.box, bd=1, relief="solid", padx=18, pady=12)
            c.grid(row=i // 4, column=i % 4, padx=8, pady=8, sticky="nsew")
            tk.Label(c, text=str(v), font=("Arial", 22, "bold")).pack()
            tk.Label(c, text=k).pack()


class DoctorPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        f = ttk.LabelFrame(self, text="Add Doctor (creates a doctor login)"); f.pack(fill="x", padx=10, pady=8)
        self.v = {k: tk.StringVar() for k in ("Name", "Specialization", "Username", "Password")}
        for i, (k, var) in enumerate(self.v.items()):
            ttk.Label(f, text=k).grid(row=0, column=i * 2, padx=4, pady=6)
            ttk.Entry(f, textvariable=var, width=16, show="*" if k == "Password" else "").grid(row=0, column=i * 2 + 1)
        ttk.Button(f, text="Add", command=self.add).grid(row=0, column=8, padx=8)
        self.tree = make_tree(self, ("id", "name", "specialization"))
        ttk.Button(self, text="Delete Selected Doctor", command=self.delete).pack(pady=4)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for d in db.doctors():
            self.tree.insert("", "end", values=(d["id"], d["name"], d["specialization"]))

    def add(self):
        v = {k: x.get().strip() for k, x in self.v.items()}
        if not all(v.values()):
            return messagebox.showerror("Error", "Fill all fields.")
        if db.add_doctor(v["Name"], v["Specialization"], v["Username"], v["Password"]):
            for x in self.dv(): x.set("")
            self.refresh()
        else:
            messagebox.showerror("Error", "Username already exists.")

    def dv(self):
        return self.v.values()

    def delete(self):
        sel = self.tree.selection()
        if sel and messagebox.askyesno("Delete", "Delete doctor and all their appointments?"):
            db.delete_doctor(self.tree.item(sel[0])["values"][0]); self.refresh()


class AvailabilityPanel(ttk.Frame):
    def __init__(self, parent, doctor_id=None):
        super().__init__(parent)
        self.fixed = doctor_id
        f = ttk.Frame(self); f.pack(fill="x", padx=10, pady=8)
        self.doc, self.day = tk.StringVar(), tk.StringVar(value=db.DAYS[0])
        self.st, self.en = tk.StringVar(value="09:00"), tk.StringVar(value="13:00")
        if doctor_id is None:
            ttk.Label(f, text="Doctor:").pack(side="left")
            self.dcb = ttk.Combobox(f, textvariable=self.doc, width=30, state="readonly"); self.dcb.pack(side="left", padx=4)
            self.dcb.bind("<<ComboboxSelected>>", lambda e: self.load())
        ttk.Combobox(f, textvariable=self.day, values=db.DAYS, width=11, state="readonly").pack(side="left", padx=4)
        ttk.Label(f, text="From").pack(side="left"); ttk.Entry(f, textvariable=self.st, width=6).pack(side="left", padx=3)
        ttk.Label(f, text="To").pack(side="left"); ttk.Entry(f, textvariable=self.en, width=6).pack(side="left", padx=3)
        ttk.Button(f, text="Add Slot", command=self.add).pack(side="left", padx=6)
        self.tree = make_tree(self, ("id", "day", "start", "end"))
        ttk.Button(self, text="Delete Selected", command=self.delete).pack(pady=4)
        self.refresh()

    def did(self):
        return self.fixed or (pid(self.doc.get()) if self.doc.get() else None)

    def refresh(self):
        if self.fixed is None:
            self.dcb["values"] = doctor_choices()
        self.load()

    def load(self):
        self.tree.delete(*self.tree.get_children())
        if self.did():
            for a in db.get_availability(self.did()):
                self.tree.insert("", "end", values=(a["id"], a["day"], a["start"], a["end"]))

    def add(self):
        from datetime import datetime
        try:
            s, e = datetime.strptime(self.st.get(), "%H:%M"), datetime.strptime(self.en.get(), "%H:%M")
            assert s < e and self.did()
        except Exception:
            return messagebox.showerror("Error", "Select a doctor and use HH:MM times (start < end).")
        db.add_availability(self.did(), self.day.get(), self.st.get(), self.en.get()); self.load()

    def delete(self):
        sel = self.tree.selection()
        if sel:
            db.delete_availability(self.tree.item(sel[0])["values"][0]); self.load()


class BookPanel(ttk.Frame):
    def __init__(self, parent, user):
        super().__init__(parent)
        self.user = user
        f = ttk.LabelFrame(self, text="Book an Appointment"); f.pack(padx=20, pady=20, anchor="w")
        self.doc, self.date, self.slot = tk.StringVar(), tk.StringVar(value=date.today().isoformat()), tk.StringVar()
        self.prio, self.reason = tk.StringVar(value="Normal"), tk.StringVar()
        self.dcb = ttk.Combobox(f, textvariable=self.doc, width=35, state="readonly")
        self.scb = ttk.Combobox(f, textvariable=self.slot, width=10, state="readonly")
        rows = [("Doctor", self.dcb), ("Date (YYYY-MM-DD)", ttk.Entry(f, textvariable=self.date, width=14)),
                ("Time Slot", self.scb),
                ("Priority", ttk.Combobox(f, textvariable=self.prio, values=db.PRIORITIES, width=10, state="readonly")),
                ("Reason", ttk.Entry(f, textvariable=self.reason, width=38))]
        for i, (lbl, w) in enumerate(rows):
            ttk.Label(f, text=lbl).grid(row=i, column=0, sticky="w", padx=8, pady=6); w.grid(row=i, column=1, sticky="w", pady=6)
        ttk.Button(f, text="Show Free Slots", command=self.slots).grid(row=2, column=2, padx=8)
        ttk.Button(f, text="Book Appointment", command=self.book).grid(row=5, column=1, pady=10, sticky="w")
        self.refresh()

    def refresh(self):
        self.dcb["values"] = doctor_choices()

    def slots(self):
        try:
            self.scb["values"] = db.free_slots(pid(self.doc.get()), self.date.get()) if self.doc.get() else []
        except ValueError:
            return messagebox.showerror("Error", "Date must be YYYY-MM-DD.")
        self.slot.set("")
        if not self.scb["values"]:
            messagebox.showinfo("Slots", "No free slots for that doctor/date.")

    def book(self):
        if not (self.doc.get() and self.slot.get()):
            return messagebox.showerror("Error", "Choose a doctor and a time slot (click Show Free Slots).")
        ok, msg = db.book(self.user["id"], pid(self.doc.get()), self.date.get(), self.slot.get(),
                          self.reason.get().strip() or "General", self.prio.get())
        (messagebox.showinfo if ok else messagebox.showerror)("Booking", msg)
        if ok:
            self.slots(); self.reason.set("")


class RegisterWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent); self.title("Patient Registration"); self.grab_set()
        self.v = {k: tk.StringVar() for k in ("Full Name", "Phone", "Username", "Password")}
        for i, (k, var) in enumerate(self.v.items()):
            ttk.Label(self, text=k).grid(row=i, column=0, padx=10, pady=6, sticky="w")
            ttk.Entry(self, textvariable=var, width=25, show="*" if k == "Password" else "").grid(row=i, column=1, padx=10)
        ttk.Button(self, text="Register", command=self.go).grid(row=4, column=1, pady=10)

    def go(self):
        v = {k: x.get().strip() for k, x in self.v.items()}
        if not (v["Full Name"] and v["Username"] and v["Password"]):
            return messagebox.showerror("Error", "Name, username and password are required.")
        ok, msg = db.register(v["Username"], v["Password"], v["Full Name"], v["Phone"])
        if ok:
            messagebox.showinfo("Done", "Registered! You can log in now."); self.destroy()
        else:
            messagebox.showerror("Error", msg)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hospital Appointment Management System"); self.geometry("1150x650")
        db.init_db(); self.login_screen()

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    def login_screen(self):
        self.clear()
        f = ttk.Frame(self); f.place(relx=0.5, rely=0.4, anchor="center")
        ttk.Label(f, text="Hospital Appointment Management", font=("Arial", 18, "bold")).grid(columnspan=2, pady=15)
        u, p = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="Username").grid(row=1, column=0, pady=5); ttk.Entry(f, textvariable=u).grid(row=1, column=1)
        ttk.Label(f, text="Password").grid(row=2, column=0, pady=5); e = ttk.Entry(f, textvariable=p, show="*"); e.grid(row=2, column=1)

        def go(_=None):
            user = db.login(u.get().strip(), p.get())
            self.home(user) if user else messagebox.showerror("Login", "Invalid username or password.")
        e.bind("<Return>", go)
        ttk.Button(f, text="Login", command=go).grid(row=3, column=1, pady=10, sticky="w")
        ttk.Button(f, text="Register as Patient", command=lambda: RegisterWindow(self)).grid(row=4, column=1, sticky="w")
        ttk.Label(f, foreground="gray", text="Demo: admin/admin123 | doc1/doctor123 | patient1/patient123").grid(columnspan=2, pady=15)

    def home(self, user):
        self.clear()
        bar = ttk.Frame(self); bar.pack(fill="x", padx=10, pady=6)
        ttk.Label(bar, text=f"Welcome, {user['full_name']}  ({user['role'].title()})", font=("Arial", 12, "bold")).pack(side="left")
        ttk.Button(bar, text="Logout", command=self.login_screen).pack(side="right")
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=5)
        role = user["role"]
        if role == "admin":
            tabs = [("Dashboard", Dashboard(nb)), ("Kanban Board", KanbanBoard(nb)), ("Doctors", DoctorPanel(nb)),
                    ("Availability", AvailabilityPanel(nb)), ("All Appointments", AppointmentTable(nb))]
        elif role == "doctor":
            d = db.doctor_of_user(user["id"])
            tabs = [("Kanban Board", KanbanBoard(nb, d["id"])), ("My Availability", AvailabilityPanel(nb, d["id"])),
                    ("Appointment History", AppointmentTable(nb, doctor=d["id"]))]
        else:
            tabs = [("Book Appointment", BookPanel(nb, user)),
                    ("My Appointments", AppointmentTable(nb, patient=user["id"], cancel=True))]
        for name, w in tabs:
            nb.add(w, text=name)
        nb.bind("<<NotebookTabChanged>>", lambda e: getattr(nb.nametowidget(nb.select()), "refresh", lambda: None)())


if __name__ == "__main__":
    App().mainloop()
