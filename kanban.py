"""Kanban Appointment Board: Booked -> Confirmed -> In Consultation -> Completed -> Cancelled.
Move cards with the arrow buttons or by dragging a card onto another column.
Every move immediately updates the appointment status in SQLite."""
import tkinter as tk
from tkinter import ttk
import database as db

PCOL = {"Normal": "#2e9e5b", "Urgent": "#e69500", "Emergency": "#d63031"}
HCOL = {"Booked": "#3498db", "Confirmed": "#8e44ad", "In Consultation": "#e67e22",
        "Completed": "#27ae60", "Cancelled": "#7f8c8d"}


class KanbanBoard(ttk.Frame):
    def __init__(self, parent, doctor_id=None):
        super().__init__(parent)
        self.doctor_id = doctor_id  # None = all doctors (admin)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        self.search, self.prio = tk.StringVar(), tk.StringVar(value="All")
        ttk.Label(top, text="Search:").pack(side="left")
        e = ttk.Entry(top, textvariable=self.search, width=25); e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda _: self.refresh())
        ttk.Label(top, text="Priority:").pack(side="left", padx=(10, 0))
        cb = ttk.Combobox(top, textvariable=self.prio, values=["All"] + db.PRIORITIES, width=10, state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right")
        ttk.Label(top, text="Tip: drag cards or use ◀ ▶  |  ⚑ changes priority", foreground="gray").pack(side="right", padx=10)
        self.stats = ttk.Label(self, font=("Arial", 10, "bold")); self.stats.pack(fill="x", padx=8)

        board = ttk.Frame(self); board.pack(fill="both", expand=True, padx=6, pady=6)
        board.rowconfigure(0, weight=1)
        self.cols = {}
        for i, s in enumerate(db.STATUSES):
            board.columnconfigure(i, weight=1, uniform="c")
            f = tk.Frame(board, bg="#ecf0f1", bd=1, relief="solid"); f.grid(row=0, column=i, sticky="nsew", padx=3)
            hdr = tk.Label(f, bg=HCOL[s], fg="white", font=("Arial", 10, "bold")); hdr.pack(fill="x")
            cv = tk.Canvas(f, bg="#ecf0f1", highlightthickness=0, width=150)
            sb = ttk.Scrollbar(f, orient="vertical", command=cv.yview)
            inner = tk.Frame(cv, bg="#ecf0f1")
            inner.bind("<Configure>", lambda e, c=cv: c.configure(scrollregion=c.bbox("all")))
            win = cv.create_window((0, 0), window=inner, anchor="nw")
            cv.bind("<Configure>", lambda e, c=cv, w=win: c.itemconfig(w, width=e.width))
            cv.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
            self.cols[s] = (f, hdr, inner)
        self.refresh()

    def refresh(self):
        rows = db.appointments(doctor=self.doctor_id, search=self.search.get().strip(), priority=self.prio.get())
        for _, _, inner in self.cols.values():
            for w in inner.winfo_children():
                w.destroy()
        counts = {s: 0 for s in db.STATUSES}
        for r in rows:
            counts[r["status"]] += 1
            self.card(self.cols[r["status"]][2], r)
        for s in db.STATUSES:
            self.cols[s][1].config(text=f"{s} ({counts[s]})")
        total, done = len(rows), counts["Completed"]
        pct = round(100 * done / total) if total else 0
        active = total - done - counts["Cancelled"]
        emerg = sum(1 for r in rows if r["priority"] == "Emergency")
        self.stats.config(text=f"Total: {total}   Active: {active}   Completed: {done} ({pct}%)   "
                               f"Cancelled: {counts['Cancelled']}   Emergency: {emerg}")

    def card(self, parent, r):
        c = tk.Frame(parent, bg="white", bd=1, relief="solid", padx=4, pady=3)
        c.pack(fill="x", padx=4, pady=3)
        tk.Frame(c, bg=PCOL[r["priority"]], height=4).pack(fill="x")
        for text, font in [(f"#{r['id']}  {r['patient_name']}", ("Arial", 9, "bold")),
                           (f"Dr. {r['doctor_name']}", ("Arial", 9)),
                           (f"{r['date']}  {r['time']}", ("Arial", 9))]:
            tk.Label(c, text=text, bg="white", font=font, anchor="w").pack(fill="x")
        tk.Label(c, text=r["priority"], bg=PCOL[r["priority"]], fg="white", font=("Arial", 8, "bold")).pack(anchor="w")
        bar = tk.Frame(c, bg="white"); bar.pack(fill="x", pady=(3, 0))
        i = db.STATUSES.index(r["status"])
        if i > 0:
            tk.Button(bar, text="◀", width=2, command=lambda: self.move(r["id"], db.STATUSES[i - 1])).pack(side="left")
        tk.Button(bar, text="⚑", width=2, command=lambda: self.cycle(r)).pack(side="left", padx=2)
        if i < len(db.STATUSES) - 1:
            tk.Button(bar, text="▶", width=2, command=lambda: self.move(r["id"], db.STATUSES[i + 1])).pack(side="right")
        self.bind_drag(c, r["id"])

    def bind_drag(self, w, aid):
        if isinstance(w, tk.Button):
            return
        w.bind("<ButtonRelease-1>", lambda e: self.drop(e, aid))
        w.configure(cursor="hand2")
        for ch in w.winfo_children():
            self.bind_drag(ch, aid)

    def drop(self, event, aid):
        for s, (f, _, _) in self.cols.items():
            x0 = f.winfo_rootx()
            if x0 <= event.x_root < x0 + f.winfo_width():
                if s != db.get_status(aid):
                    self.move(aid, s)
                return

    def move(self, aid, status):
        db.set_status(aid, status)  # status saved to SQLite
        self.refresh()

    def cycle(self, r):
        nxt = db.PRIORITIES[(db.PRIORITIES.index(r["priority"]) + 1) % len(db.PRIORITIES)]
        db.set_priority(r["id"], nxt)
        self.refresh()
