import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import subprocess
import os
import sys
import re
from pathlib import Path
import ctypes
import threading
import queue

# Fix DPI scaling/blurriness on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

def get_exiftool_path():
    #Check if exiftool is included in build, dev or PATH
    
    # If running as PyInstaller EXE
    if getattr(sys, "frozen", False):
        # Look in bundled folder
        return os.path.join(sys._MEIPASS, "bin", "exiftool.exe")
    
    # Dev environment: check local project folder first
    local_path = os.path.join(os.path.dirname(__file__), "bin", "exiftool.exe")
    if os.path.isfile(local_path):
        return local_path
    
    # Fallback to system PATH
    return "exiftool"


class ImageGeotagger:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Geotagger")
        self.root.geometry("750x600")
        self.root.resizable(True, True)

        self.selected_paths = []
        self.image_extensions = {
            '.jpg', '.jpeg', '.png', '.tiff', '.tif',
            '.cr2', '.nef', '.arw', '.dng'
        }

        self.status_queue = queue.Queue()
        self.processing_thread = None

        self.setup_ui()
        self.check_exiftool()

    # ---------------- UI ----------------

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

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
        list_frame.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox = tk.Listbox(list_frame, height=8, yscrollcommand=scrollbar.set)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=self.file_listbox.yview)

        self.clear_btn = ttk.Button(file_frame, text="Clear Selection", command=self.clear_selection, state=tk.DISABLED)
        self.clear_btn.grid(row=2, column=0, sticky="w", pady=(5, 0), padx=5)

        # Coordinates
        coord_frame = ttk.LabelFrame(main_frame, text="GPS Coordinates", padding="10")
        coord_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        coord_frame.columnconfigure(1, weight=1)

        ttk.Label(coord_frame, text="Coordinates:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.coord_var = tk.StringVar()
        self.coord_var.trace_add("write", self.validate_coord_input)
        self.coord_entry = ttk.Entry(coord_frame, textvariable=self.coord_var)
        self.coord_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.coord_entry.bind("<Button-3>", self.paste_from_clipboard)
        ttk.Button(coord_frame, text="Open Google Maps", command=self.open_google_maps).grid(row=0, column=2)
        ttk.Label(coord_frame, text="Format: latitude, longitude", font=('TkDefaultFont', 8, 'italic')).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(coord_frame, text="Right-click on location → Click coordinates → Paste above",
                  font=('TkDefaultFont', 8)).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # Progress bar with status text on top (Canvas)
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=2, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)

        self.progress_canvas = tk.Canvas(action_frame, height=30)
        self.progress_canvas.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.progress_canvas.bind("<Configure>", self.redraw_progress)

        # Buttons
        btn_action_frame = ttk.Frame(action_frame)
        btn_action_frame.grid(row=1, column=0, sticky="e")
        ttk.Button(btn_action_frame, text="Preview Command", command=self.preview_command).pack(side=tk.RIGHT, padx=5)
        self.geotag_btn = ttk.Button(btn_action_frame, text="Geotag Images", command=self.geotag_images,
                                     style="Accent.TButton")
        self.geotag_btn.pack(side=tk.RIGHT, padx=5)

        # Start queue polling for live updates
        self.root.after(100, self.process_status_queue)

        # Initialize progress variables
        self.progress_value = 0
        self.progress_total = 1
        self.progress_text = "Ready"

    # ---------------- Helpers ----------------

    def check_exiftool(self):
        try:
            subprocess.run([get_exiftool_path(), "-ver"], capture_output=True, check=True)
            self.progress_text = "Ready - ExifTool detected"
            self.redraw_progress()
        except Exception:
            messagebox.showwarning("ExifTool Not Found", "ExifTool was not found in your PATH.\n\nhttps://exiftool.org/")
            self.progress_text = "Warning: ExifTool not found"
            self.redraw_progress()

    def select_images(self):
        files = filedialog.askopenfilenames(title="Select Images",
                                            filetypes=[("Image files", "*.jpg *.jpeg *.png *.tif *.tiff *.cr2 *.nef *.arw *.dng")])
        if files:
            self.selected_paths = list(files)
            self.update_file_list()

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        images = [str(p) for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in self.image_extensions]
        if images:
            self.selected_paths = images
            self.update_file_list()
        else:
            messagebox.showinfo("No Images Found", "No supported images found.")

    def clear_selection(self):
        self.selected_paths = []
        self.update_file_list()

    def update_file_list(self):
        self.file_listbox.delete(0, tk.END)
        for p in self.selected_paths:
            self.file_listbox.insert(tk.END, p)
        self.clear_btn.config(state=tk.NORMAL if self.selected_paths else tk.DISABLED)
        self.progress_value = 0
        self.progress_total = len(self.selected_paths) or 1
        self.progress_text = f"{len(self.selected_paths)} file(s) selected"
        self.redraw_progress()

    def validate_coord_input(self, *_):
        v = self.coord_var.get()
        f = ''.join(c for c in v if c in "0123456789.-, ")[:50]
        if f != v:
            self.coord_var.set(f)

    def parse_coordinates(self, s):
        nums = re.findall(r'-?\d+\.?\d*', s)
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
            self.coord_entry.insert(0, ''.join(c for c in text if c in "0123456789.-, ")[:50])
        except tk.TclError:
            pass
        return "break"

    def open_google_maps(self):
        import webbrowser
        self.root.attributes('-topmost', True)
        webbrowser.open("https://www.google.com/maps")
        self.root.after(1000, lambda: self.root.attributes('-topmost', False))

    # ---------------- ExifTool ----------------

    def build_exiftool_batch_command(self, files, lat, lon):
        lat_ref = 'S' if lat < 0 else 'N'
        lon_ref = 'W' if lon < 0 else 'E'
        return [
            'get_exiftool_path()',
            '-overwrite_original',
            '-P',
            '-progress',
            f'-GPSLatitude={abs(lat)}',
            f'-GPSLongitude={abs(lon)}',
            f'-GPSLatitudeRef={lat_ref}',
            f'-GPSLongitudeRef={lon_ref}',
            *files
        ]

    def preview_command(self):
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Select files first.")
            return
        coords = self.parse_coordinates(self.coord_entry.get())
        if not coords:
            messagebox.showerror("Invalid Coordinates", "Invalid coordinates.")
            return
        # Only show first 2 files and "..." if more
        files_preview = self.selected_paths[:2]
        if len(self.selected_paths) > 2:
            files_preview.append("...")
        cmd_preview = self.build_exiftool_batch_command(files_preview, *coords)
        win = tk.Toplevel(self.root)
        win.title("Command Preview")
        win.geometry("600x200")
        t = tk.Text(win, wrap=tk.WORD)
        t.pack(fill=tk.BOTH, expand=True)
        t.insert("1.0", "Example batch command:\n\n" + " ".join(cmd_preview))
        t.config(state=tk.DISABLED)

    # ---------------- Live Geotagging ----------------

    def geotag_images(self):
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Select images first.")
            return
        coords = self.parse_coordinates(self.coord_entry.get())
        if not coords:
            messagebox.showerror("Invalid Coordinates", "Invalid coordinates.")
            return
        lat, lon = coords
        if not messagebox.askyesno("Confirm Geotagging",
                                   f"Geotag {len(self.selected_paths)} files?\n\nLatitude: {lat}\nLongitude: {lon}"):
            return
        self.geotag_btn.config(state=tk.DISABLED)
        self.progress_value = 0
        self.progress_total = len(self.selected_paths)
        self.progress_text = f"Processing 0/{self.progress_total}"
        self.redraw_progress()
        self.processing_thread = threading.Thread(target=self._geotag_thread_progress, args=(lat, lon), daemon=True)
        self.processing_thread.start()

    def _geotag_thread_progress(self, lat, lon):
        files = self.selected_paths.copy()
        total = len(files)
        success_count = 0
        fail_count = 0
        cmd = self.build_exiftool_batch_command(files, lat, lon)

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if line.startswith("========"):
                    m = re.search(r'\[(\d+)/(\d+)\]', line)
                    if m:
                        processed = int(m.group(1))
                        self.status_queue.put(("PROGRESS", processed, total))
                elif "image files updated" in line.lower():
                    success_count = int(line.split()[0])
            process.wait()
        except Exception as e:
            fail_count = total
            print(f"Exception: {e}")

        self.status_queue.put(("DONE", success_count, total - success_count))

    # ---------------- Progress Canvas ----------------

    def redraw_progress(self, *_):
        canvas = self.progress_canvas
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        fill_width = int((self.progress_value / max(self.progress_total, 1)) * w)

        # Ensure canvas has a white background
        canvas.configure(bg="white")

        # Draw slightly inset border for visibility
        inset = 1
        canvas.create_rectangle(inset, inset, w - inset, h - inset, outline="#888888", width=1)

        # Draw green progress
        canvas.create_rectangle(inset, inset, fill_width, h - inset, fill="#4caf50", width=0)

        # Draw text on top in black
        canvas.create_text(w // 2, h // 2, text=self.progress_text, fill="black", font=("TkDefaultFont", 10, "bold"))


    def process_status_queue(self):
        try:
            while True:
                msg = self.status_queue.get_nowait()
                if isinstance(msg, tuple):
                    if msg[0] == "PROGRESS":
                        processed, total = msg[1], msg[2]
                        self.progress_value = processed
                        self.progress_total = total
                        self.progress_text = f"Processing {processed}/{total}"
                        self.redraw_progress()
                    elif msg[0] == "DONE":
                        success, failed = msg[1], msg[2]
                        self.progress_value = self.progress_total
                        self.progress_text = f"Complete: {success} succeeded, {failed} failed"
                        self.redraw_progress()
                        messagebox.showinfo("Geotagging Complete",
                                            f"Total files: {success + failed}\nSuccessfully geotagged: {success}\nFailed: {failed}")
                        self.geotag_btn.config(state=tk.NORMAL)
                        self.selected_paths = []
                        self.update_file_list()
        except queue.Empty:
            pass
        self.root.after(100, self.process_status_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageGeotagger(root)
    root.mainloop()
