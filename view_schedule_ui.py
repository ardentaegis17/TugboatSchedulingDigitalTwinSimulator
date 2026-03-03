import json
import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import os

# Configuration
INPUT_FILE = "cheap_insertion_tabu.json"

class CompactScheduleViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tug Schedule Viewer (With Metrics)")
        self.geometry("1400x800")

        # 1. Main Layout
        self.main_frame = tk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=1)

        self.canvas = tk.Canvas(self.main_frame, bg="white")
        self.v_scroll = ttk.Scrollbar(self.main_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self.main_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.content_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        self.load_data()

    def load_data(self):
        if not os.path.exists(INPUT_FILE):
            messagebox.showerror("Error", f"File not found: {INPUT_FILE}")
            return

        with open(INPUT_FILE, 'r') as f:
            raw_data = json.load(f)
            jobs = raw_data['jobs'] if isinstance(raw_data, dict) else raw_data

        # Group by Tug
        tug_schedule = {i: [] for i in range(1, 16)}
        for job in jobs:
            for tug_id_str in job.get('tugImos', []):
                try:
                    tid = int(tug_id_str)
                    if tid in tug_schedule:
                        tug_schedule[tid].append(job)
                except: pass

        # Draw Rows
        for tug_id in range(1, 16):
            self.draw_tug_row(tug_id, tug_schedule[tug_id])

    def draw_tug_row(self, tug_id, jobs):
        row_frame = tk.Frame(self.content_frame, bg="white", bd=0)
        row_frame.pack(fill=tk.X, expand=True, padx=2, pady=1)

        # --- METRICS CALCULATION ---
        # Sum the 'predictedWait' for every job this tug touches
        total_wait_seconds = sum(j.get('predictedWait', 0) for j in jobs)
        total_wait_mins = total_wait_seconds / 60.0
        
        # Color Code the Header based on performance
        header_bg = "#ddd" # Gray (Good)
        if total_wait_mins > 100: header_bg = "#ffcc80" # Orange (Warning)
        if total_wait_mins > 200: header_bg = "#ef9a9a" # Red (Critical)

        # --- LEFT HEADER (Tug ID + Metrics) ---
        # We create a sub-frame for the header to stack text vertically or side-by-side
        header_frame = tk.Frame(row_frame, bg=header_bg, width=120, height=40)
        header_frame.pack_propagate(False) # Force size
        header_frame.pack(side=tk.LEFT, padx=(0, 2))

        # Tug ID Label
        tk.Label(header_frame, text=f"Tug {tug_id}", bg=header_bg, font=("Arial", 10, "bold")).pack(pady=(2,0))
        
        # Total Wait Label
        wait_text = f"Wait: {int(total_wait_mins)}m"
        tk.Label(header_frame, text=wait_text, bg=header_bg, font=("Arial", 8)).pack()

        # --- RIGHT CONTENT (Timeline) ---
        jobs.sort(key=lambda x: x['predictedStartTime'])
        for job in jobs:
            self.draw_job_card(row_frame, job)

    def draw_job_card(self, parent, job):
        wait = job.get('predictedWait', 0)
        
        # Card Color Logic
        bg_color = "#e3f2fd"
        if wait > 3600: bg_color = "#ffcdd2"
        elif wait > 1800: bg_color = "#fff9c4"

        card = tk.Frame(parent, bg=bg_color, bd=1, relief=tk.SOLID, padx=4, pady=2)
        card.pack(side=tk.LEFT, padx=1)

        # Time formatting
        start_seconds = job['predictedStartTime']
        m, s = divmod(start_seconds, 60)
        h, m = divmod(m, 60)
        time_str = f"{int(h):02d}:{int(m):02d}"

        # Text: "JOB_001 | 12:00 (+15m)"
        # Shows job ID, Start Time, and specific delay for this job
        delay_str = f"+{int(wait/60)}m" if wait > 0 else ""
        label_text = f"{job['jobId']}\n{time_str} {delay_str}"
        
        tk.Label(card, text=label_text, bg=bg_color, font=("Consolas", 8), justify=tk.LEFT).pack()

if __name__ == "__main__":
    app = CompactScheduleViewer()
    app.mainloop()