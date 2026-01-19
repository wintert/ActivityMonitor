"""
Project Tags view UI for ActivityMonitor.
Allows users to define project tags for grouping activities.
"""

from typing import Optional, Callable, Dict, List
import logging

import tkinter as tk
from tkinter import messagebox, colorchooser

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    from ttkbootstrap import Toplevel
    from ttkbootstrap.dialogs import Messagebox
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    from tkinter import ttk
    Toplevel = tk.Toplevel
    Messagebox = None
    TTKBOOTSTRAP_AVAILABLE = False

logger = logging.getLogger(__name__)


class ProjectTagsView:
    """
    Project Tags dialog for defining project groupings.

    Allows users to define tags with keyword patterns that group
    activities from different tools (Visual Studio, Claude Code, Terminal)
    under a single project heading.
    """

    DEFAULT_COLORS = [
        '#4A90D9',  # Blue
        '#50C878',  # Green
        '#FF6B6B',  # Red
        '#9B59B6',  # Purple
        '#F39C12',  # Orange
        '#1ABC9C',  # Teal
        '#E74C3C',  # Dark Red
        '#3498DB',  # Light Blue
        '#2ECC71',  # Emerald
        '#E67E22',  # Dark Orange
    ]

    def __init__(self, database, parent: Optional[tk.Tk] = None,
                 on_change: Optional[Callable] = None):
        self.db = database
        self.parent = parent
        self.on_change = on_change  # Called when tags are added/edited/deleted
        self.window: Optional[tk.Toplevel] = None
        self._selected_tag_id: Optional[int] = None
        self._color_index = 0

    def show(self):
        """Show the project tags window."""
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self.window.deiconify()
                    self.window.lift()
                    self.window.focus_force()
                    self._refresh_list()
                    return
            except Exception:
                self.window = None

        self._create_window()
        self._refresh_list()

        # Force window to be visible
        self.window.deiconify()
        self.window.attributes('-topmost', True)
        self.window.lift()
        self.window.focus_force()
        self.window.update()
        self.window.attributes('-topmost', False)

    def _create_window(self):
        """Create the project tags window."""
        if self.parent:
            self.window = Toplevel(self.parent)
        else:
            if TTKBOOTSTRAP_AVAILABLE:
                from ttkbootstrap import Window
                self.window = Window(themename="darkly")
            else:
                self.window = tk.Toplevel()

        self.window.title("ActivityMonitor - Project Tags")
        self.window.geometry("700x550")
        self.window.resizable(True, True)

        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Main container
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Description
        desc_label = ttk.Label(
            main_frame,
            text="Define project tags to group activities from different tools. "
                 "Activities containing any keyword will be tagged with that project.",
            font=('Segoe UI', 9),
            foreground='#888',
            wraplength=650
        )
        desc_label.pack(anchor='w', pady=(0, 10))

        # Create list section
        self._create_list_section(main_frame)

        # Create form section
        self._create_form_section(main_frame)

        # Create buttons
        self._create_buttons(main_frame)

    def _create_list_section(self, parent):
        """Create the project tags list."""
        list_frame = ttk.LabelFrame(parent, text="Project Tags")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Treeview
        columns = ('name', 'keywords', 'color', 'enabled')
        self._tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=8)

        self._tree.heading('name', text='Name')
        self._tree.heading('keywords', text='Keywords')
        self._tree.heading('color', text='Color')
        self._tree.heading('enabled', text='Enabled')

        self._tree.column('name', width=150, minwidth=100)
        self._tree.column('keywords', width=300, minwidth=150)
        self._tree.column('color', width=80, minwidth=60, anchor='center')
        self._tree.column('enabled', width=60, minwidth=50, anchor='center')

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind selection
        self._tree.bind('<<TreeviewSelect>>', self._on_select)
        self._tree.bind('<Double-1>', self._on_double_click)

    def _create_form_section(self, parent):
        """Create the add/edit form."""
        form_frame = ttk.LabelFrame(parent, text="Add / Edit Project Tag")
        form_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Name
        row1 = ttk.Frame(form_frame)
        row1.pack(fill=tk.X, pady=5, padx=10)

        ttk.Label(row1, text="Name:", width=12, anchor='w').pack(side=tk.LEFT)
        self._name_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._name_var, width=30).pack(side=tk.LEFT, padx=(0, 20))

        self._enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="Enabled", variable=self._enabled_var).pack(side=tk.LEFT)

        # Row 2: Keywords
        row2 = ttk.Frame(form_frame)
        row2.pack(fill=tk.X, pady=5, padx=10)

        ttk.Label(row2, text="Keywords:", width=12, anchor='w').pack(side=tk.LEFT)
        self._keywords_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self._keywords_var, width=50).pack(side=tk.LEFT)

        # Row 3: Color
        row3 = ttk.Frame(form_frame)
        row3.pack(fill=tk.X, pady=5, padx=10)

        ttk.Label(row3, text="Color:", width=12, anchor='w').pack(side=tk.LEFT)

        self._color_var = tk.StringVar(value=self.DEFAULT_COLORS[0])
        self._color_preview = tk.Label(row3, text='     ', bg=self._color_var.get(), width=5)
        self._color_preview.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(row3, text="Choose Color", command=self._choose_color, width=12).pack(side=tk.LEFT)

        # Quick color buttons
        ttk.Label(row3, text="Quick:", width=6, anchor='w').pack(side=tk.LEFT, padx=(10, 0))
        for i, color in enumerate(self.DEFAULT_COLORS[:5]):
            btn = tk.Label(row3, text='  ', bg=color, cursor='hand2')
            btn.pack(side=tk.LEFT, padx=2)
            btn.bind('<Button-1>', lambda e, c=color: self._set_color(c))

        # Row 4: Action buttons
        row4 = ttk.Frame(form_frame)
        row4.pack(fill=tk.X, pady=(5, 10), padx=10)

        self._add_btn = ttk.Button(row4, text="Add", command=self._add_tag, width=10)
        self._add_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._update_btn = ttk.Button(row4, text="Update", command=self._update_tag, width=10, state='disabled')
        self._update_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._delete_btn = ttk.Button(row4, text="Delete", command=self._delete_tag, width=10, state='disabled')
        self._delete_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(row4, text="Clear Form", command=self._clear_form, width=10).pack(side=tk.LEFT)

        # Help text
        help_text = ttk.Label(
            form_frame,
            text="Keywords are comma-separated (e.g., 'SiiNewUmbraco, SiiNew'). "
                 "Activities containing any keyword will be grouped under this project.",
            font=('Segoe UI', 8),
            foreground='#666',
            wraplength=600
        )
        help_text.pack(anchor='w', padx=10, pady=(0, 5))

    def _create_buttons(self, parent):
        """Create bottom buttons."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Close", command=self.close).pack(side=tk.RIGHT)

    def _refresh_list(self):
        """Refresh the project tags list."""
        # Clear existing items
        for item in self._tree.get_children():
            self._tree.delete(item)

        # Load tags from database
        tags = self.db.get_project_tags()

        for tag in tags:
            keywords_str = ', '.join(tag['keywords'])
            enabled_display = 'Yes' if tag['enabled'] else 'No'

            self._tree.insert('', tk.END,
                iid=str(tag['id']),
                values=(
                    tag['name'],
                    keywords_str,
                    tag['color'],
                    enabled_display
                ),
                tags=(tag['color'],)
            )

            # Try to apply color to the row (may not work with all themes)
            try:
                self._tree.tag_configure(tag['color'], foreground=tag['color'])
            except Exception:
                pass

    def _on_select(self, event):
        """Handle selection in the list."""
        selection = self._tree.selection()
        if selection:
            self._selected_tag_id = int(selection[0])
            self._load_tag_to_form(self._selected_tag_id)
            self._update_btn.config(state='normal')
            self._delete_btn.config(state='normal')
        else:
            self._selected_tag_id = None
            self._update_btn.config(state='disabled')
            self._delete_btn.config(state='disabled')

    def _on_double_click(self, event):
        """Handle double-click to edit."""
        self._on_select(event)

    def _load_tag_to_form(self, tag_id: int):
        """Load a tag into the form for editing."""
        tags = self.db.get_project_tags()
        for tag in tags:
            if tag['id'] == tag_id:
                self._name_var.set(tag['name'])
                self._keywords_var.set(', '.join(tag['keywords']))
                self._set_color(tag['color'])
                self._enabled_var.set(tag['enabled'])
                break

    def _choose_color(self):
        """Open color chooser dialog."""
        color = colorchooser.askcolor(
            initialcolor=self._color_var.get(),
            title="Choose Project Color",
            parent=self.window
        )
        if color[1]:  # color is ((r,g,b), '#hexcode')
            self._set_color(color[1])

    def _set_color(self, color: str):
        """Set the selected color."""
        self._color_var.set(color)
        self._color_preview.configure(bg=color)

    def _get_next_color(self) -> str:
        """Get the next default color in rotation."""
        color = self.DEFAULT_COLORS[self._color_index % len(self.DEFAULT_COLORS)]
        self._color_index += 1
        return color

    def _add_tag(self):
        """Add a new project tag."""
        name = self._name_var.get().strip()
        keywords_str = self._keywords_var.get().strip()
        color = self._color_var.get()
        enabled = self._enabled_var.get()

        if not name:
            self._show_error("Validation Error", "Name is required.")
            return

        if not keywords_str:
            self._show_error("Validation Error", "At least one keyword is required.")
            return

        # Parse keywords
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

        if not keywords:
            self._show_error("Validation Error", "At least one keyword is required.")
            return

        try:
            self.db.add_project_tag(name, keywords, color, enabled)
            self._refresh_list()
            self._clear_form()
            self._notify_change()
            self._show_info("Success", f"Project tag '{name}' added.")
        except Exception as e:
            if 'UNIQUE constraint failed' in str(e):
                self._show_error("Error", f"A project tag named '{name}' already exists.")
            else:
                self._show_error("Error", f"Failed to add tag: {e}")

    def _update_tag(self):
        """Update the selected project tag."""
        if self._selected_tag_id is None:
            return

        name = self._name_var.get().strip()
        keywords_str = self._keywords_var.get().strip()
        color = self._color_var.get()
        enabled = self._enabled_var.get()

        if not name:
            self._show_error("Validation Error", "Name is required.")
            return

        if not keywords_str:
            self._show_error("Validation Error", "At least one keyword is required.")
            return

        # Parse keywords
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

        if not keywords:
            self._show_error("Validation Error", "At least one keyword is required.")
            return

        try:
            self.db.update_project_tag(
                self._selected_tag_id,
                name=name,
                keywords=keywords,
                color=color,
                enabled=enabled
            )
            self._refresh_list()
            self._clear_form()
            self._notify_change()
            self._show_info("Success", "Project tag updated successfully.")
        except Exception as e:
            self._show_error("Error", f"Failed to update tag: {e}")

    def _delete_tag(self):
        """Delete the selected project tag."""
        if self._selected_tag_id is None:
            return

        if not self._show_yesno("Confirm Delete", "Are you sure you want to delete this project tag?"):
            return

        try:
            self.db.delete_project_tag(self._selected_tag_id)
            self._refresh_list()
            self._clear_form()
            self._notify_change()
        except Exception as e:
            self._show_error("Error", f"Failed to delete tag: {e}")

    def _clear_form(self):
        """Clear the form fields."""
        self._name_var.set('')
        self._keywords_var.set('')
        self._set_color(self._get_next_color())
        self._enabled_var.set(True)
        self._selected_tag_id = None
        self._update_btn.config(state='disabled')
        self._delete_btn.config(state='disabled')

        # Clear selection in tree
        for item in self._tree.selection():
            self._tree.selection_remove(item)

    def _notify_change(self):
        """Notify that tags have changed."""
        if self.on_change:
            self.on_change()

    def _show_info(self, title: str, message: str):
        """Show info message."""
        if TTKBOOTSTRAP_AVAILABLE and Messagebox:
            Messagebox.show_info(message, title=title, parent=self.window)
        else:
            messagebox.showinfo(title, message)

    def _show_error(self, title: str, message: str):
        """Show error message."""
        if TTKBOOTSTRAP_AVAILABLE and Messagebox:
            Messagebox.show_error(message, title=title, parent=self.window)
        else:
            messagebox.showerror(title, message)

    def _show_yesno(self, title: str, message: str) -> bool:
        """Show yes/no dialog."""
        if TTKBOOTSTRAP_AVAILABLE and Messagebox:
            return Messagebox.yesno(message, title=title, parent=self.window) == "Yes"
        else:
            return messagebox.askyesno(title, message)

    def close(self):
        """Close the window."""
        if self.window:
            self.window.destroy()
            self.window = None
