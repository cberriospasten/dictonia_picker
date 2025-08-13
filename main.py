import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageOps, ImageFilter
import numpy as np
import csv
import os
from skimage import filters, measure

class ImagePickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DicTonia Picker v1.0")
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        # Menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load Image", command=self.load_image, accelerator="Ctrl+O")
        file_menu.add_command(label="Close Image", command=self.clear_image)
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV", command=self.export_csv, accelerator="Ctrl+S")
        area_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Observation Area", menu=area_menu)
        area_menu.add_command(label="Detect Area", command=self.detect_observation_area)
        area_menu.add_command(label="Edit Area", command=self.enable_observation_area_edit)
        front_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Feeding Front", menu=front_menu)
        front_menu.add_command(label="Draw Front", command=self.start_feeding_polygon_draw)
        front_menu.add_command(label="Clear Front", command=self.clear_feeding_front)
        picker_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Picker", menu=picker_menu)
        picker_menu.add_command(label="Activate Picker", command=self.activate_picker)
        picker_menu.add_command(label="Clear Points", command=self.clear_points)
        self.stop_button = tk.Button(self.root, text="■ Finish Drawing / Editing", command=self.stop_current_mode, bg="#e74c3c", fg="white", relief=tk.FLAT, font=("Helvetica", 10, "bold"))        
        self.status_label = tk.Label(self.root, text="Load an image to start", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas = tk.Canvas(self.root, cursor="arrow", background="gray20") # <-- MODIFICADO: cursor por defecto
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Control-MouseWheel>", self.on_zoom)
        self.canvas.bind("<Alt-ButtonPress-1>", self.start_pan)
        self.canvas.bind("<Alt-B1-Motion>", self.perform_pan)
        self.canvas.bind("<Alt-ButtonRelease-1>", self.end_pan)
        self.root.bind("<Control-o>", lambda e: self.load_image())
        self.root.bind("<Control-s>", lambda e: self.export_csv())
        self.original_image = None
        self.zoom_factor, self.offset = 1.0, [0, 0]
        self.points, self.feeding_polygon = [], []
        self.observation_center_orig, self.observation_radius_orig = None, None
        self.current_mode = None
        self.label_menu = tk.Menu(self.root, tearoff=0)
        for label in ["radius", "mound", "finger", "slug", "fruiting body"]:
            self.label_menu.add_command(label=label, command=lambda l=label: self.add_point(l))
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.set_neutral_mode()

    def set_neutral_mode(self):
        self.current_mode = 'neutral'
        self.canvas.config(cursor="arrow") # Cursor normal
        # Desvincular acciones de clic para evitar clics accidentales
        for i in ["<Button-1>", "<Button-3>", "<B1-Motion>", "<ButtonRelease-1>"]:
            self.canvas.unbind(i)
        self.update_status("Ready. Select an option from the menu.")
    
    def stop_current_mode(self):
        if self.current_mode == 'draw_front':
            self.finish_polygon_draw()
        elif self.current_mode == 'edit_area':
            self.end_observation_edit()
        
        self.stop_button.pack_forget()
        self.set_neutral_mode()

    def set_mode(self, mode_name):
        self.current_mode = mode_name
        for i in ["<Button-1>", "<Button-3>", "<B1-Motion>", "<ButtonRelease-1>"]: self.canvas.unbind(i)
        self.stop_button.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        
    def activate_picker(self):
        self.set_mode('picker') # Configurar el modo formalmente
        self.stop_button.pack_forget() # El picker no necesita botón de stop
        self.canvas.config(cursor="cross")
        self.canvas.bind("<Button-1>", self.on_click_picker)
        self.canvas.bind("<Button-3>", self.on_right_click_picker)
        self.update_status("Picker Mode: Left-click to label a point, Right-click to delete.")
    
    def load_image(self):
        f_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.tif *.tiff")])
        if not f_path: return
        try:
            self.original_image = Image.open(f_path).convert("RGB"); self.image_path = f_path; self.clear_all_annotations(); self.fit_to_window()
            # <-- MODIFICADO: Mensaje de estado neutral
            self.update_status(f"Image loaded: {os.path.basename(self.image_path)}. Select an option from the menu.")
        except Exception as e: messagebox.showerror("Error", f"Could not load image: {e}")
    
    def on_click_picker(self, event):
        if not self.original_image: return
        self.click_position = self.canvas_to_orig(event.x, event.y)
        try: self.label_menu.tk_popup(event.x_root, event.y_root)
        finally: self.label_menu.grab_release()

    def on_right_click_picker(self, event):
        if not self.original_image: return
        click_x, click_y = self.canvas_to_orig(event.x, event.y)
        for i, (_, x, y) in enumerate(self.points):
            if ((x - click_x)**2 + (y - click_y)**2)**0.5 < (10 / self.zoom_factor):
                del self.points[i]; self.update_display_image(); return

    def enable_observation_area_edit(self):
        if not self.observation_center_orig: messagebox.showwarning("No Area", "No area detected to edit."); return
        self.set_mode('edit_area')
        self.canvas.config(cursor="hand2")
        self.canvas.bind("<Button-1>", self.start_observation_edit)
        self.canvas.bind("<B1-Motion>", self.perform_observation_edit)
        self.canvas.bind("<ButtonRelease-1>", self.end_observation_edit)
        self.update_status("Edit Area Mode: Drag to edit. Press 'Finish' button when done.")
        
    def start_feeding_polygon_draw(self):
        if not self.original_image: messagebox.showwarning("No Image", "Please load an image first."); return
        self.set_mode('draw_front')
        self.canvas.config(cursor="tcross")
        self.feeding_polygon = []
        self.canvas.bind("<Button-1>", self.add_polygon_point)
        self.update_status("Draw Front Mode: Left-click to add points. Press 'Finish' button when done.")
        
    def finish_polygon_draw(self):
        if len(self.feeding_polygon) > 0:
            if len(self.feeding_polygon) < 3:
                messagebox.showwarning("Invalid Polygon", "At least 3 points are required. Polygon discarded.")
                self.feeding_polygon = []
            else:
                self.update_status("Polygon drawing finished.")
        self.update_display_image()
        
    def end_observation_edit(self, event=None): self.edit_mode = None
    
    def add_point(self, label): self.points.append((label, *self.click_position)); self.update_display_image()
    def add_polygon_point(self, event): self.feeding_polygon.append(self.canvas_to_orig(event.x, event.y)); self.update_display_image()
    
    def update_status(self, msg): self.status_label.config(text=msg)

    def clear_image(self): self.original_image = None; self.canvas.delete("all"); self.clear_all_annotations(); self.set_neutral_mode()
    def clear_all_annotations(self):
        self.points, self.feeding_polygon = [], []; self.observation_center_orig, self.observation_radius_orig = None, None
        if self.original_image: self.update_display_image()
    def clear_points(self): self.points = []; self.update_display_image()
    def clear_feeding_front(self): self.feeding_polygon = []; self.update_display_image()
    
    def fit_to_window(self):
        if not self.original_image: return
        cw, ch, iw, ih = self.canvas.winfo_width(), self.canvas.winfo_height(), self.original_image.width, self.original_image.height
        if iw == 0 or ih == 0: return
        self.zoom_factor = min(cw / iw, ch / ih); new_w, new_h = iw*self.zoom_factor, ih*self.zoom_factor
        self.offset = [(cw - new_w)/2, (ch - new_h)/2]; self.update_display_image()

    def update_display_image(self):
        if not self.original_image: self.canvas.delete("all"); return
        new_size = (int(self.original_image.width * self.zoom_factor), int(self.original_image.height * self.zoom_factor))
        if new_size[0] < 1 or new_size[1] < 1: return
        img = self.original_image.resize(new_size, Image.Resampling.LANCZOS); draw = ImageDraw.Draw(img); z = self.zoom_factor
        if self.observation_center_orig and self.observation_radius_orig:
            cx, cy, r = self.observation_center_orig[0], self.observation_center_orig[1], self.observation_radius_orig
            draw.ellipse(((cx-r)*z, (cy-r)*z, (cx+r)*z, (cy+r)*z), outline="yellow", width=2)
        cmap = {"center":"black", "mound":"orange", "finger":"cyan", "slug":"red", "fruiting body":"darkgreen"}
        for lbl, x, y in self.points: draw.ellipse(((x*z)-5, (y*z)-5, (x*z)+5, (y*z)+5), fill=cmap.get(lbl, "white"))
        if self.feeding_polygon: draw.line([(x*z, y*z) for x, y in self.feeding_polygon] + [(self.feeding_polygon[0][0]*z, self.feeding_polygon[0][1]*z)], fill="purple", width=2)
        self.tk_image = ImageTk.PhotoImage(img); self.canvas.delete("all"); self.canvas.create_image(self.offset[0], self.offset[1], anchor="nw", image=self.tk_image)

    def on_zoom(self, e):
        if not self.original_image: return
        factor = 1.1 if e.delta > 0 else 1/1.1; new_zoom = self.zoom_factor * factor
        mx, my = e.x - self.offset[0], e.y - self.offset[1]
        self.offset = [e.x - mx*factor, e.y - my*factor]; self.zoom_factor = new_zoom; self.update_display_image()
    def start_pan(self, e): self.pan_start = (e.x, e.y); self.canvas.config(cursor="fleur")
    def perform_pan(self, e):
        dx, dy = e.x - self.pan_start[0], e.y - self.pan_start[1]; self.offset = [self.offset[0]+dx, self.offset[1]+dy]
        self.pan_start = (e.x, e.y); self.update_display_image()
    def end_pan(self, e): self.canvas.config(cursor="arrow") # Volver a cursor neutral
    def canvas_to_orig(self, x, y): return (x-self.offset[0])/self.zoom_factor, (y-self.offset[1])/self.zoom_factor
    def on_canvas_resize(self, e): self.fit_to_window()
    
    def export_csv(self):
        if not self.image_path: messagebox.showwarning("No Data", "No image loaded."); return
        f_path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{os.path.splitext(os.path.basename(self.image_path))[0]}_analysis.csv", filetypes=[("CSV files", "*.csv")])
        if not f_path: return
        with open(f_path, 'w', newline='') as f:
            w = csv.writer(f)
            if self.observation_center_orig: w.writerow(["# OBSERVATION AREA (Circle)"]); w.writerow(["# cx","cy","radius"]); w.writerow([f"{c:.2f}" for c in self.observation_center_orig]+[f"{self.observation_radius_orig:.2f}"]); w.writerow([])
            if self.feeding_polygon: w.writerow(["# FEEDING FRONT (Polygon Points)"]); w.writerow(["# x","y"]); w.writerows(self.feeding_polygon); w.writerow([]); w.writerow(["# FEEDING FRONT CENTER"]); w.writerow(["# cx","cy"]); w.writerow([f"{c:.2f}" for c in np.mean(self.feeding_polygon,axis=0)]); w.writerow([])
            if self.points: w.writerow(["# LABELED POINTS"]); w.writerow(["# label","x","y"]); w.writerows(self.points)
        messagebox.showinfo("Success", f"Data exported to {f_path}")

    def detect_observation_area(self):
        if not self.original_image: return
        arr = np.array(self.original_image.convert('L').filter(ImageFilter.GaussianBlur(5)))
        regions = measure.regionprops(measure.label(arr > filters.threshold_otsu(arr)))
        if not regions: messagebox.showerror("Detection Failed", "No regions detected."); return
        largest = max(regions, key=lambda r:r.area); cy, cx = largest.centroid; r = max(largest.major_axis_length, largest.minor_axis_length)/2
        self.observation_center_orig, self.observation_radius_orig = (cx, cy), r; self.update_display_image()
        
    def start_observation_edit(self, e):
        x, y = self.canvas_to_orig(e.x, e.y); cx, cy = self.observation_center_orig; r = self.observation_radius_orig
        dist = ((x-cx)**2 + (y-cy)**2)**0.5
        if dist < r: self.edit_mode = 'move'
        elif abs(dist-r) < (10/self.zoom_factor): self.edit_mode = 'resize'
        else: self.edit_mode = None
        self.last_mouse_orig = (x, y)

    def perform_observation_edit(self, e):
        if not hasattr(self, 'edit_mode') or self.edit_mode is None: return
        x, y = self.canvas_to_orig(e.x, e.y); dx, dy = x-self.last_mouse_orig[0], y-self.last_mouse_orig[1]
        if self.edit_mode == 'move': self.observation_center_orig = (self.observation_center_orig[0]+dx, self.observation_center_orig[1]+dy)
        elif self.edit_mode == 'resize':
            new_r = ((x-self.observation_center_orig[0])**2 + (y-self.observation_center_orig[1])**2)**0.5
            if new_r*self.zoom_factor > 5: self.observation_radius_orig = new_r
        self.last_mouse_orig = (x, y); self.update_display_image()
        
    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"): self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ImagePickerApp(root)
    root.geometry("1200x800")
    root.mainloop()
