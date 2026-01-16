import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
import re
from pathlib import Path
import ctypes

# Fix DPI scaling/blurriness on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

class ImageGeotagger:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Geotagger")
        self.root.geometry("700x550")
        self.root.resizable(True, True)
        
        self.selected_paths = []
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.cr2', '.nef', '.arw', '.dng'}
        
        self.setup_ui()
        self.check_exiftool()
    
    def setup_ui(self):
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # File selection section
        file_frame = ttk.LabelFrame(main_frame, text="Select Images", padding="10")
        file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)
        
        btn_frame = ttk.Frame(file_frame)
        btn_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        ttk.Button(btn_frame, text="Select Images", command=self.select_images).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Select Folder", command=self.select_folder).pack(side=tk.LEFT, padx=5)
        
        # Listbox with scrollbar for selected files
        list_frame = ttk.Frame(file_frame)
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.file_listbox = tk.Listbox(list_frame, height=8, yscrollcommand=scrollbar.set)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)
        
        # Clear button below listbox
        self.clear_btn = ttk.Button(file_frame, text="Clear Selection", command=self.clear_selection, state=tk.DISABLED)
        self.clear_btn.grid(row=2, column=0, sticky=tk.W, pady=(5, 0), padx=5)
        
        # Coordinates section
        coord_frame = ttk.LabelFrame(main_frame, text="GPS Coordinates", padding="10")
        coord_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        coord_frame.columnconfigure(1, weight=1)
        
        ttk.Label(coord_frame, text="Coordinates:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        # Create StringVar with validation
        self.coord_var = tk.StringVar()
        self.coord_var.trace_add('write', self.validate_coord_input)
        
        self.coord_entry = ttk.Entry(coord_frame, width=40, textvariable=self.coord_var)
        self.coord_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        self.coord_entry.bind('<Button-3>', self.paste_from_clipboard)  # Right-click to paste
        
        ttk.Button(coord_frame, text="Open Google Maps", command=self.open_google_maps).grid(row=0, column=2)
        
        ttk.Label(coord_frame, text="Format: latitude, longitude", font=('TkDefaultFont', 8, 'italic')).grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(5, 0)
        )
        
        # Instructions
        instructions_text = "Right-click on location → Click coordinates → Paste above"
        ttk.Label(coord_frame, text=instructions_text, font=('TkDefaultFont', 8)).grid(
            row=2, column=0, columnspan=3, sticky=tk.W, pady=(2, 0)
        )
        
        # Status and action section
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.S))
        action_frame.columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(action_frame, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        btn_action_frame = ttk.Frame(action_frame)
        btn_action_frame.grid(row=1, column=0, sticky=tk.E)
        
        self.geotag_btn = ttk.Button(btn_action_frame, text="Geotag Images", command=self.geotag_images, 
                                      style='Accent.TButton')
        self.geotag_btn.pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(btn_action_frame, text="Preview Command", command=self.preview_command).pack(side=tk.RIGHT, padx=5)
    
    def check_exiftool(self):
        """Check if exiftool is available"""
        try:
            subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
            self.status_label.config(text="Ready - ExifTool detected")
        except (subprocess.CalledProcessError, FileNotFoundError):
            messagebox.showwarning(
                "ExifTool Not Found",
                "ExifTool was not found in your system PATH.\n\n"
                "Please install ExifTool from:\n"
                "https://exiftool.org/\n\n"
                "After installation, make sure it's added to your PATH."
            )
            self.status_label.config(text="Warning: ExifTool not found")
    
    def select_images(self):
        """Open file dialog to select multiple images"""
        filetypes = [
            ("Image files", "*.jpg *.jpeg *.png *.tiff *.tif *.cr2 *.nef *.arw *.dng"),
            ("All files", "*.*")
        ]
        files = filedialog.askopenfilenames(title="Select Images", filetypes=filetypes)
        if files:
            self.selected_paths = list(files)
            self.update_file_list()
    
    def select_folder(self):
        """Open folder dialog and find all images in the folder"""
        folder = filedialog.askdirectory(title="Select Folder Containing Images")
        if folder:
            image_files = []
            for file in Path(folder).iterdir():
                if file.is_file() and file.suffix.lower() in self.image_extensions:
                    image_files.append(str(file))
            
            if image_files:
                self.selected_paths = image_files
                self.update_file_list()
            else:
                messagebox.showinfo("No Images Found", "No supported image files found in the selected folder.")
    
    def clear_selection(self):
        """Clear the selected files"""
        self.selected_paths = []
        self.update_file_list()
    
    def update_file_list(self):
        """Update the listbox with selected files"""
        self.file_listbox.delete(0, tk.END)
        for path in self.selected_paths:
            self.file_listbox.insert(tk.END, path)
        self.status_label.config(text=f"{len(self.selected_paths)} file(s) selected")
        
        # Enable/disable clear button based on selection
        if self.selected_paths:
            self.clear_btn.config(state=tk.NORMAL)
        else:
            self.clear_btn.config(state=tk.DISABLED)
    
    def validate_coord_input(self, *args):
        """Validate coordinate entry - only allow numbers, dots, minus signs, commas, and spaces. Limit to 50 chars"""
        value = self.coord_var.get()
        
        # Filter out invalid characters - only allow: digits, dots, minus, comma, space
        filtered = ''.join(char for char in value if char in '0123456789.-, ')
        
        # Limit to 50 characters
        if len(filtered) > 50:
            filtered = filtered[:50]
        
        # Only update if the value changed (prevents infinite loop)
        if filtered != value:
            self.coord_var.set(filtered)
    
    def parse_coordinates(self, coord_string):
        """Parse coordinates from various formats"""
        # Remove whitespace
        coord_string = coord_string.strip()
        
        # Try to extract numbers (including negative signs and decimals)
        numbers = re.findall(r'-?\d+\.?\d*', coord_string)
        
        if len(numbers) >= 2:
            try:
                lat = float(numbers[0])
                lon = float(numbers[1])
                
                # Validate ranges
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
                else:
                    raise ValueError("Coordinates out of range")
            except ValueError:
                return None
        return None
    
    def paste_from_clipboard(self, event=None):
        """Paste coordinates from clipboard when right-clicking the entry field"""
        try:
            clipboard_content = self.root.clipboard_get()
            # Filter to only allowed characters and limit to 50
            filtered = ''.join(char for char in clipboard_content if char in '0123456789.-, ')[:50]
            self.coord_entry.delete(0, tk.END)
            self.coord_entry.insert(0, filtered)
        except tk.TclError:
            # Clipboard is empty or unavailable
            pass
        return "break"  # Prevent default right-click menu
    
    def open_google_maps(self):
        """Open Google Maps in browser"""
        import webbrowser
        
        # Temporarily set main window to stay on top
        self.root.attributes('-topmost', True)
        
        webbrowser.open("https://www.google.com/maps")
        
        # After 2 seconds, remove the topmost attribute
        self.root.after(1000, lambda: self.root.attributes('-topmost', False))
    
    def build_exiftool_command(self, file_path, lat, lon):
        """Build the exiftool command for a single file"""
        lat_ref = 'S' if lat < 0 else 'N'
        lon_ref = 'W' if lon < 0 else 'E'
        
        # ExifTool expects positive values with separate reference tags
        abs_lat = abs(lat)
        abs_lon = abs(lon)
        
        cmd = [
            'exiftool',
            '-overwrite_original',
            '-P',
            f'-GPSLatitude={abs_lat}',
            f'-GPSLongitude={abs_lon}',
            f'-GPSLatitudeRef={lat_ref}',
            f'-GPSLongitudeRef={lon_ref}',
            file_path
        ]
        return cmd
    
    def preview_command(self):
        """Show a preview of the exiftool command"""
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Please select images first.")
            return
        
        coords = self.parse_coordinates(self.coord_entry.get())
        if not coords:
            messagebox.showerror("Invalid Coordinates", "Please enter valid coordinates in the format: latitude, longitude")
            return
        
        lat, lon = coords
        sample_file = self.selected_paths[0]
        cmd = self.build_exiftool_command(sample_file, lat, lon)
        
        # Create preview window
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Command Preview")
        preview_window.geometry("600x200")
        
        text_widget = tk.Text(preview_window, wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        text_widget.insert('1.0', "Example command for first file:\n\n")
        text_widget.insert(tk.END, ' '.join(cmd))
        text_widget.config(state=tk.DISABLED)
    
    def geotag_images(self):
        """Execute the geotagging process"""
        if not self.selected_paths:
            messagebox.showwarning("No Files", "Please select images to geotag.")
            return
        
        coords = self.parse_coordinates(self.coord_entry.get())
        if not coords:
            messagebox.showerror("Invalid Coordinates", "Please enter valid coordinates in the format: latitude, longitude")
            return
        
        lat, lon = coords
        
        # Confirm action
        result = messagebox.askyesno(
            "Confirm Geotagging",
            f"Geotag {len(self.selected_paths)} file(s) with coordinates:\n"
            f"Latitude: {lat}\n"
            f"Longitude: {lon}\n\n"
            "This will modify the files. Continue?"
        )
        
        if not result:
            return
        
        # Process files
        success_count = 0
        fail_count = 0
        
        self.geotag_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Processing...")
        self.root.update()
        
        for i, file_path in enumerate(self.selected_paths):
            try:
                cmd = self.build_exiftool_command(file_path, lat, lon)
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                success_count += 1
                self.status_label.config(text=f"Processing... ({i+1}/{len(self.selected_paths)})")
                self.root.update()
            except subprocess.CalledProcessError as e:
                fail_count += 1
                print(f"Failed to process {file_path}: {e.stderr}")
        
        self.geotag_btn.config(state=tk.NORMAL)
        self.status_label.config(text=f"Complete: {success_count} succeeded, {fail_count} failed")
        
        messagebox.showinfo(
            "Geotagging Complete",
            f"Successfully geotagged: {success_count}\n"
            f"Failed: {fail_count}"
        )
        
        # Clear selection and coordinates only if all files were successful
        if fail_count == 0 and success_count > 0:
            self.selected_paths = []
            self.update_file_list()
            self.coord_entry.delete(0, tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageGeotagger(root)
    root.mainloop()