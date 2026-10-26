# gui.py - Tkinter user interface (drawing only, the protocol is in protocol.py)
import tkinter as tk
from tkinter import messagebox
from protocol import Simulation
from channel import LOST, CORRUPT

TICK_MS = 30                       # the GUI updates every 30 ms using after()
CANVAS_W, CANVAS_H = 960, 300
X_START, X_END = 160, 800          # left / right end of the channel on the canvas
LANE_H = 24
DATA_LANES, DATA_Y0 = 6, 55        # frames travel in the upper lanes
ACK_LANES, ACK_Y0 = 3, 240         # ACKs travel back in the lower lanes
PANEL_W, PANEL_H = 470, 120

COLORS = {
    "frame": "#1976d2",     # normal frame
    "retx": "#ef6c00",      # retransmitted frame
    "corrupt": "#c2185b",   # corrupted frame / ACK
    "lost": "#d32f2f",      # lost frame / ACK
    "ack": "#2e7d32",       # acknowledgement
    "buffer": "#fdd835",    # buffered frame (receiver)
}

LOG_COLORS = {
    "send": "#1565c0", "retx": "#e65100", "recv": "#2e7d32", "ack": "#00796b",
    "lost": "#c62828", "corrupt": "#ad1457", "timeout": "#bf360c",
    "buffer": "#9e7a00", "deliver": "#1b5e20", "dup": "#616161", "info": "#37474f",
}


class SimulatorApp:
    def __init__(self, root):
        self.root = root
        root.title("Selective Repeat ARQ Protocol Simulator")
        self.sim = None
        self.state = "idle"          # idle / running / paused / finished
        self.after_id = None
        self.input_widgets = []

        self.build_controls()
        self.build_network()
        self.build_windows()
        self.build_log_and_stats()

        self.set_state("idle")
        self.refresh()

    # ================= building the screen =================
    def build_controls(self):
        box = tk.LabelFrame(self.root, text="A. Control Panel", padx=8, pady=4)
        box.pack(fill="x", padx=8, pady=4)

        self.frames_var = tk.StringVar(value="12")
        self.window_var = tk.StringVar(value="4")
        self.loss_var = tk.IntVar(value=20)
        self.corrupt_var = tk.IntVar(value=10)
        self.delay_var = tk.IntVar(value=1200)

        tk.Label(box, text="Number of frames (1-100):").grid(row=0, column=0, sticky="e")
        s1 = tk.Spinbox(box, from_=1, to=100, width=5, textvariable=self.frames_var)
        s1.grid(row=0, column=1, padx=4)

        tk.Label(box, text="Window size (1-16):").grid(row=0, column=2, sticky="e")
        s2 = tk.Spinbox(box, from_=1, to=16, width=5, textvariable=self.window_var)
        s2.grid(row=0, column=3, padx=4)

        tk.Label(box, text="Loss %:").grid(row=0, column=4, sticky="e")
        sc1 = tk.Scale(box, from_=0, to=60, resolution=5, orient="horizontal",
                       length=110, variable=self.loss_var)
        sc1.grid(row=0, column=5, padx=4)

        tk.Label(box, text="Corruption %:").grid(row=0, column=6, sticky="e")
        sc2 = tk.Scale(box, from_=0, to=60, resolution=5, orient="horizontal",
                       length=110, variable=self.corrupt_var)
        sc2.grid(row=0, column=7, padx=4)

        tk.Label(box, text="Channel delay (ms):").grid(row=0, column=8, sticky="e")
        sc3 = tk.Scale(box, from_=200, to=3000, resolution=100, orient="horizontal",
                       length=130, variable=self.delay_var)
        sc3.grid(row=0, column=9, padx=4)

        self.input_widgets = [s1, s2, sc1, sc2, sc3]

        buttons = tk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=10, sticky="w", pady=4)
        self.start_btn = tk.Button(buttons, text="Start Simulation", width=16, command=self.on_start)
        self.start_btn.pack(side="left", padx=4)
        self.pause_btn = tk.Button(buttons, text="Pause", width=10, command=self.on_pause)
        self.pause_btn.pack(side="left", padx=4)
        self.reset_btn = tk.Button(buttons, text="Reset", width=10, command=self.on_reset)
        self.reset_btn.pack(side="left", padx=4)
        self.status_var = tk.StringVar()
        tk.Label(buttons, textvariable=self.status_var, font=("Arial", 10, "bold")).pack(side="left", padx=20)

    def build_network(self):
        box = tk.LabelFrame(self.root, text="B. Network Visualization", padx=4, pady=4)
        box.pack(fill="x", padx=8, pady=4)
        self.canvas = tk.Canvas(box, width=CANVAS_W, height=CANVAS_H, bg="white")
        self.canvas.pack()
        c = self.canvas

        # sender and receiver boxes
        c.create_rectangle(10, 40, 130, 290, fill="#bbdefb", outline="black", width=2)
        c.create_text(70, 165, text="SENDER", font=("Arial", 12, "bold"))
        c.create_rectangle(835, 40, 950, 290, fill="#c8e6c9", outline="black", width=2)
        c.create_text(892, 165, text="RECEIVER", font=("Arial", 12, "bold"))

        # the noisy channel with one thin arrow per lane
        c.create_text((X_START + X_END) // 2, 14, text="NOISY CHANNEL", font=("Arial", 12, "bold"), fill="#555")
        for i in range(DATA_LANES):
            y = DATA_Y0 + i * LANE_H
            c.create_line(X_START, y, X_END + 25, y, fill="#dddddd", dash=(2, 4), arrow=tk.LAST)
        c.create_text((X_START + X_END) // 2, 30, text="Data frames  ---->", fill="#777")
        c.create_line(X_START, 205, X_END + 25, 205, fill="#999")
        c.create_text((X_START + X_END) // 2, 217, text="<----  ACKs", fill="#777")
        for i in range(ACK_LANES):
            y = ACK_Y0 + i * LANE_H
            c.create_line(X_START - 25, y, X_END, y, fill="#dddddd", dash=(2, 4), arrow=tk.FIRST)

        # legend
        legend = tk.Frame(box)
        legend.pack(pady=2)
        items = [("Frame", "frame"), ("Retransmitted", "retx"), ("Corrupted (!)", "corrupt"),
                 ("Lost (X)", "lost"), ("ACK", "ack")]
        for text, key in items:
            tk.Label(legend, text=text, bg=COLORS[key], fg="white", padx=8).pack(side="left", padx=4)
        tk.Label(legend, text="Buffered (receiver)", bg=COLORS["buffer"], padx=8).pack(side="left", padx=4)

    def build_windows(self):
        row = tk.Frame(self.root)
        row.pack(fill="x", padx=8, pady=4)

        left = tk.LabelFrame(row, text="C. Sender Window", padx=4, pady=4)
        left.pack(side="left", expand=True, fill="both", padx=(0, 4))
        self.sender_canvas = tk.Canvas(left, width=PANEL_W, height=PANEL_H, bg="white")
        self.sender_canvas.pack()

        right = tk.LabelFrame(row, text="D. Receiver Window", padx=4, pady=4)
        right.pack(side="left", expand=True, fill="both", padx=(4, 0))
        self.receiver_canvas = tk.Canvas(right, width=PANEL_W, height=PANEL_H, bg="white")
        self.receiver_canvas.pack()

    def build_log_and_stats(self):
        row = tk.Frame(self.root)
        row.pack(fill="both", expand=True, padx=8, pady=4)

        # event log
        log_box = tk.LabelFrame(row, text="E. Event Log", padx=4, pady=4)
        log_box.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.log_text = tk.Text(log_box, height=9, width=80, state="disabled", font=("Courier", 9))
        scroll = tk.Scrollbar(log_box, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for tag, color in LOG_COLORS.items():
            self.log_text.tag_config(tag, foreground=color)

        # statistics
        stat_box = tk.LabelFrame(row, text="F. Statistics", padx=8, pady=4)
        stat_box.pack(side="left", fill="y", padx=(4, 0))
        self.stat_vars = {}
        rows = [("Total frames", "total"), ("Delivered frames", "delivered"),
                ("Lost frames", "lost"), ("Corrupted frames", "corrupted"),
                ("Retransmissions", "retx"), ("ACKs sent / received", "acks"),
                ("Timeouts", "timeouts"), ("Duplicates at receiver", "dups"),
                ("Throughput", "throughput"), ("Efficiency", "efficiency"),
                ("Simulation time", "time")]
        for i, (label, key) in enumerate(rows):
            tk.Label(stat_box, text=label + ":", anchor="w").grid(row=i, column=0, sticky="w")
            var = tk.StringVar(value="0")
            tk.Label(stat_box, textvariable=var, anchor="e", width=16,
                     font=("Arial", 9, "bold")).grid(row=i, column=1, sticky="e", padx=(10, 0))
            self.stat_vars[key] = var

    # ================= buttons =================
    def read_inputs(self):
        try:
            n = int(self.frames_var.get())
            w = int(self.window_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Number of frames and window size must be whole numbers.")
            return None
        if not 1 <= n <= 100:
            messagebox.showerror("Invalid input", "Number of frames must be between 1 and 100.")
            return None
        if not 1 <= w <= 16:
            messagebox.showerror("Invalid input", "Window size must be between 1 and 16.")
            return None
        loss = self.loss_var.get() / 100.0
        corrupt = self.corrupt_var.get() / 100.0
        if loss + corrupt > 0.9:
            messagebox.showerror("Invalid input", "Loss % + Corruption % must not be more than 90.")
            return None
        return n, w, loss, corrupt, self.delay_var.get()

    def on_start(self):
        params = self.read_inputs()
        if params is None:
            return
        self.clear_log()
        self.sim = Simulation(*params)
        self.sim.log("Simulation started: %d frames, window size %d" % (params[0], params[1]), "info")
        self.set_state("running")
        self.tick()

    def on_pause(self):
        if self.state == "running":
            if self.after_id is not None:
                self.root.after_cancel(self.after_id)
                self.after_id = None
            self.set_state("paused")
        elif self.state == "paused":
            self.set_state("running")
            self.tick()

    def on_reset(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.sim = None
        self.clear_log()
        self.set_state("idle")
        self.refresh()

    def set_state(self, state):
        self.state = state
        active = state in ("running", "paused")
        for w in self.input_widgets:
            w.config(state="disabled" if active else "normal")
        self.start_btn.config(state="disabled" if active else "normal")
        self.pause_btn.config(state="normal" if active else "disabled",
                              text="Resume" if state == "paused" else "Pause")
        names = {"idle": "Status: Ready", "running": "Status: Running",
                 "paused": "Status: Paused", "finished": "Status: Finished"}
        self.status_var.set(names[state])

    # ================= main loop (uses after(), never blocks) =================
    def tick(self):
        if self.state != "running":
            return
        self.sim.step(TICK_MS)
        self.refresh()
        if self.sim.done:
            self.set_state("finished")
        else:
            self.after_id = self.root.after(TICK_MS, self.tick)

    # ================= drawing =================
    def refresh(self):
        self.draw_packets()
        self.draw_sender_window()
        self.draw_receiver_window()
        self.update_log()
        self.update_stats()

    def draw_packets(self):
        c = self.canvas
        c.delete("dyn")
        if self.sim is None:
            return
        for p in self.sim.packets:
            prog = p.progress(self.sim.now)
            if p.kind == "DATA":
                x = X_START + prog * (X_END - X_START)
                y = DATA_Y0 + (p.seq % DATA_LANES) * LANE_H
                name = "F%d" % p.seq
                fill = COLORS["retx"] if p.retransmit else COLORS["frame"]
            else:
                x = X_END - prog * (X_END - X_START)
                y = ACK_Y0 + (p.seq % ACK_LANES) * LANE_H
                name = "A%d" % p.seq
                fill = COLORS["ack"]
            text = name
            if p.fate == CORRUPT:
                fill = COLORS["corrupt"]
                text = name + " !"
            if p.fate == LOST and p.handled:      # reached the point where it was lost
                fill = COLORS["lost"]
                text = name + " X"
            c.create_rectangle(x - 26, y - 9, x + 26, y + 9, fill=fill, outline="black", tags="dyn")
            c.create_text(x, y, text=text, fill="white", font=("Arial", 8, "bold"), tags="dyn")

    def draw_boxes(self, canvas, first, total, state_of):
        """Draw the window as a row of boxes: frame number + status text."""
        count = min(self.window_size(), total - first)
        if count <= 0:
            canvas.create_text(PANEL_W // 2, 50, text="(window is empty - all frames done)")
            return 0
        box_w = min(50, (PANEL_W - 20) // self.window_size())
        for i in range(count):
            seq = first + i
            fill, text = state_of(seq)
            x0 = 10 + i * box_w
            canvas.create_rectangle(x0, 28, x0 + box_w - 3, 72, fill=fill, outline="black")
            canvas.create_text(x0 + (box_w - 3) / 2, 40, text=str(seq), font=("Arial", 10, "bold"))
            canvas.create_text(x0 + (box_w - 3) / 2, 60, text=text, font=("Arial", 7))
        canvas.create_rectangle(7, 25, 10 + count * box_w, 75, outline="#1565c0", width=2)
        return count

    def window_size(self):
        return self.sim.window if self.sim else 1

    def draw_sender_window(self):
        c = self.sender_canvas
        c.delete("all")
        if self.sim is None:
            c.create_text(PANEL_W // 2, PANEL_H // 2, text="Simulation not started", fill="#888")
            return
        s = self.sim.sender
        c.create_text(10, 12, anchor="w", font=("Arial", 9, "bold"),
                      text="base = %d     next_seq = %d     window size = %d" % (s.base, s.next_seq, s.window))

        def state_of(seq):
            st = s.status(seq)
            if st == "acked":
                return "#a5d6a7", "ACK"
            if st == "sent":
                return "#ffcc80", "SENT"
            return "#ffffff", "-"

        self.draw_boxes(c, s.base, s.total, state_of)
        unacked = [q for q in range(s.base, s.next_seq) if not s.acked[q]]
        c.create_text(10, 92, anchor="w", font=("Arial", 9),
                      text="Sent but not ACKed: " + (", ".join(map(str, unacked)) if unacked else "none"))
        c.create_text(10, 108, anchor="w", font=("Arial", 8), fill="#666",
                      text="green = ACKed, orange = sent/unacknowledged, white = not sent yet")

    def draw_receiver_window(self):
        c = self.receiver_canvas
        c.delete("all")
        if self.sim is None:
            c.create_text(PANEL_W // 2, PANEL_H // 2, text="Simulation not started", fill="#888")
            return
        r = self.sim.receiver
        c.create_text(10, 12, anchor="w", font=("Arial", 9, "bold"),
                      text="rcv_base = %d (next frame expected)     window size = %d" % (r.rcv_base, r.window))

        def state_of(seq):
            if seq in r.buffer:
                return COLORS["buffer"], "BUFFERED"
            return "#ffffff", "WAIT"

        self.draw_boxes(c, r.rcv_base, r.total, state_of)
        buffered = sorted(r.buffer)
        c.create_text(10, 92, anchor="w", font=("Arial", 9),
                      text="Buffered: " + (", ".join(map(str, buffered)) if buffered else "none"))
        last = r.delivered[-12:]
        prefix = "... " if len(r.delivered) > 12 else ""
        c.create_text(10, 108, anchor="w", font=("Arial", 9),
                      text="Delivered (%d): %s%s" % (len(r.delivered), prefix, " ".join(map(str, last))))

    # ================= log and statistics =================
    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def update_log(self):
        if self.sim is None or not self.sim.events:
            return
        self.log_text.config(state="normal")
        for t, text, tag in self.sim.events:
            self.log_text.insert("end", "[%6.2fs] %s\n" % (t / 1000.0, text), tag)
        self.sim.events.clear()
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def update_stats(self):
        v = self.stat_vars
        if self.sim is None:
            for key in v:
                v[key].set("0")
            v["throughput"].set("0.00 frames/s")
            v["efficiency"].set("0.0 %")
            v["time"].set("0.00 s")
            return
        sim = self.sim
        st = sim.stats
        delivered = len(sim.receiver.delivered)
        seconds = sim.now / 1000.0
        throughput = delivered / seconds if seconds > 0 else 0.0
        efficiency = 100.0 * delivered / st.sent if st.sent > 0 else 0.0

        v["total"].set(str(sim.total))
        v["delivered"].set(str(delivered))
        v["lost"].set(str(st.lost))
        v["corrupted"].set(str(st.corrupted))
        v["retx"].set(str(st.retransmissions))
        v["acks"].set("%d / %d" % (st.acks_sent, st.acks_received))
        v["timeouts"].set(str(st.timeouts))
        v["dups"].set(str(sim.receiver.duplicates))
        v["throughput"].set("%.2f frames/s" % throughput)
        v["efficiency"].set("%.1f %%" % efficiency)
        v["time"].set("%.2f s" % seconds)