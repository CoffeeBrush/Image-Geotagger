import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
import shutil
import subprocess
from pathlib import Path
import ctypes
import threading
import queue
import re

# Fix DPI scaling/blurriness on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def get_exiftool_path(filename="exiftool.exe"):
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        path = os.path.join(exe_dir, "bin", filename)
        if os.path.isfile(path):
            return path

    script_dir = os.path.dirname(__file__)
    path = os.path.join(script_dir, "bin", filename)
    if os.path.isfile(path):
        return path

    found = shutil.which(filename)
    if found:
        return found

    return filename


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.geometry(f"+{x}+{y}")
        ttk.Label(
            self.tip,
            text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padding=6
        ).pack()

    def hide(self, _):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class ImageGeotagger:
    PROGRESS_REGEX = None

    def __init__(self, root):
        self.root = root
        self.root.title("Image Geotagger")
        self.root.geometry("750x650")
        self.root.resizable(True, True)

        self.exiftool_path = get_exiftool_path("exiftool.exe")

        icon_path = get_exiftool_path("icon.ico")
        if os.path.isfile(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self.selected_paths = []
        self.image_extensions = {
            ".jpg", ".jpeg", ".png", ".tiff", ".tif",
            ".cr2", ".nef", ".arw", ".dng"
        }

        self.status_queue = queue.Queue()
        self.processing_thread = None

        self.progress_value = 0
        self.progress_total = 1
        self.progress_text = "Loading"

        self.time_offset_var = tk.StringVar(value="+00:00")

        self.timezone_offsets = {
            "UTC": 0,
            "GMT": 0,
            "NZST": 12,
            "NZDT": 13,
            "AEST": 10,
            "AEDT": 11,
            "JST": 9,
            "PST": -8,
            "EST": -5,
            "CET": 1
        }

        self.setup_ui()

        self.root.after(100, self.check_exiftool)
        self.root.after(100, self.process_status_queue)

    # ---------------- UI ----------------

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # File selection
        file_frame = ttk.LabelFrame(main_frame, text="Select Images", padding="10")
        file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(file_frame)
        btn_frame.grid(row=0, column=0, sticky="w")
        ttk.Button(btn_frame, text="Select Images", command=self.select_images).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Select Folder", command=self.select_folder).pack(side=tk.LEFT, padx=5)

        list_frame = ttk.Frame(file_frame)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        list_frame.columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox = tk.Listbox(list_frame, height=8, yscrollcommand=scrollbar.set)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=self.file_listbox.yview)

        self.clear_btn = ttk.Button(file_frame, text="Clear Selection",
                                    command=self.clear_selection, state=tk.DISABLED)
        self.clear_btn.grid(row=2, column=0, sticky="w", pady=(5, 0))

        # Coordinates
        coord_frame = ttk.LabelFrame(main_frame, text="GPS Coordinates", padding="10")
        coord_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        coord_frame.columnconfigure(1, weight=1)

        ttk.Label(coord_frame, text="Coordinates:").grid(row=0, column=0, sticky="w")
        self.coord_var = tk.StringVar()
        self.coord_entry = ttk.Entry(coord_frame, textvariable=self.coord_var)
        self.coord_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ttk.Button(coord_frame, text="Open Google Maps", command=self.open_google_maps).grid(row=0, column=2)

        ttk.Label(coord_frame, text="Format: latitude, longitude", font=('TkDefaultFont', 8, 'italic')) \
            .grid(row=1, column=0, columnspan=3, sticky="w")

        ttk.Label(
            coord_frame,
            text="Open Google Maps → Right-click → Click coordinates → Paste here",
            font=('TkDefaultFont', 8)
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        # Time correction
        time_frame = ttk.LabelFrame(main_frame, text="Correct Image Time", padding="10")
        time_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self.from_tz_var = tk.StringVar(value="UTC")
        self.to_tz_var = tk.StringVar(value="UTC")

        ttk.Label(time_frame, text="From:").grid(row=0, column=0)
        self.from_tz_combo = ttk.Combobox(
            time_frame, values=list(self.timezone_offsets.keys()),
            textvariable=self.from_tz_var, state="readonly", width=8
        )
        self.from_tz_combo.grid(row=0, column=1)

        ttk.Label(time_frame, text="To:").grid(row=0, column=2, padx=(10, 0))
        self.to_tz_combo = ttk.Combobox(
            time_frame, values=list(self.timezone_offsets.keys()),
            textvariable=self.to_tz_var, state="readonly", width=8
        )
        self.to_tz_combo.grid(row=0, column=3)

        ttk.Label(time_frame, text="Offset:").grid(row=0, column=4, padx=(10, 0))
        self.offset_entry = ttk.Entry(time_frame, textvariable=self.time_offset_var, width=8)
        self.offset_entry.grid(row=0, column=5)

        ToolTip(
            self.offset_entry,
            "Time offset applied to all images.\n"
            "Auto-calculated from timezones.\n"
            "Editable for camera drift or DST fixes.\n\n"
            "Format: +HH:MM or -HH:MM"
        )

        self.from_tz_combo.bind("<<ComboboxSelected>>", lambda e: self.update_time_offset())
        self.to_tz_combo.bind("<<ComboboxSelected>>", lambda e: self.update_time_offset())

        # Progress + actions
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=3, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)

        self.progress_canvas = tk.Canvas(action_frame, height=30, bg="white", highlightthickness=0)
        self.progress_canvas.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.progress_canvas.bind("<Configure>", self.redraw_progress)

        btn_action_frame = ttk.Frame(action_frame)
        btn_action_frame.grid(row=1, column=0, sticky="e")

        ttk.Button(btn_action_frame, text="Correct Image Time", command=self.correct_image_time) \
            .pack(side=tk.RIGHT, padx=5)

        self.geotag_btn = ttk.Button(btn_action_frame, text="Geotag Images", command=self.geotag_images)
        self.geotag_btn.pack(side=tk.RIGHT, padx=5)

        self.redraw_progress()

    # ---------------- Time helpers ----------------

    def update_time_offset(self):
        try:
            delta = self.timezone_offsets[self.to_tz_var.get()] - self.timezone_offsets[self.from_tz_var.get()]
            sign = "+" if delta >= 0 else "-"
            self.time_offset_var.set(f"{sign}{abs(delta):02d}:00")
        except Exception:
            pass

    def validate_offset(self):
        return re.match(r"^[+-]\d{2}:\d{2}$", self.time_offset_var.get().strip())

    # ---------------- ExifTool time correction ----------------

    def correct_image_time(self):
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Select images first.")
            return

        if not self.validate_offset():
            messagebox.showerror(
                "Invalid Offset",
                "Offset must be in the format:\n\n+HH:MM or -HH:MM\n\nExample: +12:00"
            )
            return

        offset = self.time_offset_var.get().strip()
        files = tuple(self.selected_paths)

        self.progress_value = 0
        self.progress_total = len(files)
        self.progress_text = "Processing 0/{}".format(self.progress_total)
        self.redraw_progress()

        threading.Thread(
            target=self._time_correction_thread,
            args=(offset, files),
            daemon=True
        ).start()

    def _time_correction_thread(self, offset, files):
        cmd = [
            self.exiftool_path,
            f"-AllDates+={offset}",
            "-overwrite_original",
            "-progress",
            *files
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=CREATE_NO_WINDOW
            )
            for line in process.stdout:
                m = re.search(r"\[(\d+)/(\d+)\]", line)
                if m:
                    self.status_queue.put(("PROGRESS", int(m.group(1)), int(m.group(2))))
            process.wait()
        except Exception:
            pass

        self.status_queue.put(("DONE", len(files), 0))

    # ---------------- Helpers ----------------

    def check_exiftool(self):
        try:
            subprocess.run([get_exiftool_path(), "-ver"],
                capture_output=True,
                check=True,
                creationflags=CREATE_NO_WINDOW)
            self.progress_text = "Ready"
        except Exception:
            messagebox.showwarning(
                "ExifTool Not Found",
                "ExifTool was not found. Install from: \n\nhttps://exiftool.org/"
            )
            self.progress_text = "Warning: ExifTool not found"
        self.redraw_progress()

    def add_to_queue(self, paths):
        # Add new file paths to the selection without duplicates.
        existing = set(self.selected_paths)
        added = False

        for p in paths:
            if p not in existing:
                self.selected_paths.append(p)
                existing.add(p)
                added = True

        if added:
            self.update_file_list()

    def select_images(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.cr2 *.nef *.arw *.dng")]
        )
        if files:
            self.add_to_queue(list(files))

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        images = [
            str(p) for p in Path(folder).rglob("*")
            if p.is_file() and p.suffix.lower() in self.image_extensions
        ]
        if images:
            self.add_to_queue(images)
        else:
            messagebox.showinfo("No Images Found", "No supported images found in this folder or its subfolders.")

    def clear_selection(self):
        self.selected_paths = []
        self.update_file_list()

    def update_file_list(self):
        self.file_listbox.delete(0, tk.END)
        for p in self.selected_paths:
            self.file_listbox.insert(tk.END, p)
        self.clear_btn.config(state=tk.NORMAL if self.selected_paths else tk.DISABLED)
        self.progress_value = 0
        self.progress_total = max(len(self.selected_paths), 1)
        self.progress_text = f"{len(self.selected_paths)} file(s) selected"
        self.redraw_progress()

    def validate_coord_input(self, *_):
        v = self.coord_var.get()
        f = "".join(c for c in v if c in "0123456789.-, ")[:50]
        if f != v:
            self.coord_var.set(f)

    def parse_coordinates(self, s):
        import re
        nums = re.findall(r"-?\d+\.?\d*", s)
        if len(nums) < 2:
            return None
        lat, lon = map(float, nums[:2])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
        return None

    def paste_from_clipboard(self, _):
        try:
            text = self.root.clipboard_get()
            self.coord_entry.delete(0, tk.END)
            self.coord_entry.insert(0, "".join(c for c in text if c in "0123456789.-, ")[:50])
        except tk.TclError:
            pass
        return "break"

    def open_google_maps(self):
        import webbrowser
        self.root.attributes("-topmost", True)
        webbrowser.open("https://www.google.com/maps")
        self.root.after(1000, lambda: self.root.attributes("-topmost", False))

    # ---------------- ExifTool ----------------

    def build_exiftool_batch_command(self, files, lat, lon):
        lat_ref = "S" if lat < 0 else "N"
        lon_ref = "W" if lon < 0 else "E"
        return [
            self.exiftool_path,
            "-overwrite_original",
            "-P",
            "-progress",
            f"-GPSLatitude={abs(lat)}",
            f"-GPSLongitude={abs(lon)}",
            f"-GPSLatitudeRef={lat_ref}",
            f"-GPSLongitudeRef={lon_ref}",
            *files,
        ]

    def preview_command(self):
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Select files first.")
            return
        coords = self.parse_coordinates(self.coord_entry.get())
        if not coords:
            messagebox.showerror("Invalid Coordinates", "Invalid coordinates.")
            return

        preview_files = self.selected_paths[:2]
        if len(self.selected_paths) > 2:
            preview_files.append("...")

        cmd = self.build_exiftool_batch_command(preview_files, *coords)

        win = tk.Toplevel(self.root)
        win.title("Command Preview")
        win.geometry("600x200")
        text = tk.Text(win, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert("1.0", " ".join(cmd))
        text.config(state=tk.DISABLED)

    # ---------------- Geotagging ----------------

    def geotag_images(self):
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Select images first.")
            return
        coords = self.parse_coordinates(self.coord_entry.get())
        if not coords:
            messagebox.showerror("Invalid Coordinates", "Invalid coordinates.")
            return

        lat, lon = coords
        if not messagebox.askyesno(
            "Confirm Geotagging",
            f"Geotag {len(self.selected_paths)} files?\n\nLatitude: {lat}\nLongitude: {lon}"
        ):
            return

        self.geotag_btn.config(state=tk.DISABLED)
        self.progress_value = 0
        self.progress_total = len(self.selected_paths)
        self.progress_text = f"Processing 0/{self.progress_total}"
        self.redraw_progress()

        self.processing_thread = threading.Thread(
            target=self._geotag_thread_progress, args=(lat, lon), daemon=True
        )
        self.processing_thread.start()

    def _geotag_thread_progress(self, lat, lon):
        import re

        if self.PROGRESS_REGEX is None:
            self.PROGRESS_REGEX = re.compile(r"\[(\d+)/(\d+)\]")

        files = tuple(self.selected_paths)
        total = len(files)
        success = 0

        cmd = self.build_exiftool_batch_command(files, lat, lon)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            )
            for line in process.stdout:
                m = self.PROGRESS_REGEX.search(line)
                if m:
                    self.status_queue.put(("PROGRESS", int(m.group(1)), total))
                elif "image files updated" in line.lower():
                    success = int(line.split()[0])
            process.wait()
        except Exception:
            pass

        self.status_queue.put(("DONE", success, total - success))

    # ---------------- Progress Canvas ----------------

    def redraw_progress(self, *_):
        c = self.progress_canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        fill = int((self.progress_value / max(self.progress_total, 1)) * w)

        c.create_rectangle(1, 1, w - 1, h - 1, outline="#999999", width=1)
        if self.progress_value > 0:
            c.create_rectangle(1, 1, fill, h - 1, fill="#4caf50", width=0) # only draw status when in progress
        c.create_text(w // 2, h // 2, text=self.progress_text,
                      fill="black", font=("TkDefaultFont", 10, "bold"))

    def process_status_queue(self):
        try:
            while True:
                msg = self.status_queue.get_nowait()
                if msg[0] == "PROGRESS":
                    if msg[1] != self.progress_value:
                        self.progress_value = msg[1]
                        self.progress_text = f"Processing {msg[1]}/{msg[2]}"
                        self.redraw_progress()
                elif msg[0] == "DONE":
                    self.progress_value = self.progress_total
                    self.progress_text = f"Complete: {msg[1]} succeeded, {msg[2]} failed"
                    self.redraw_progress()
                    messagebox.showinfo(
                        "Geotagging Complete",
                        f"Total files: {msg[1] + msg[2]}\n"
                        f"Successfully Processed: {msg[1]}\n"
                        f"Failed: {msg[2]}"
                    )
                    self.geotag_btn.config(state=tk.NORMAL)
        except queue.Empty:
            pass

        self.root.after(100, self.process_status_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageGeotagger(root)
    root.mainloop()
