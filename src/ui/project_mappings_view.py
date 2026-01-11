"""
Project Mappings view UI for ActivityMonitor.
Allows users to define custom display name mappings for projects.
"""

from typing import Optional, Callable, Dict, List
import logging

import tkinter as tk
from tkinter import messagebox

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


class ProjectMappingsView:
    """
    Project Mappings dialog for defining custom display names.

    Allows users to map:
    - Process names (e.g., "devenv.exe" → "Visual Studio")
    - Project names (e.g., "EwaveShamirUmbraco13" → "Shamir Website")
    - Window title patterns
    """

    MATCH_TYPES = {
        'process': 'Process Name',
        'project': 'Project Name',
        'window': 'Window Title'
    }

    def __init__(self, database, project_mapper, parent: Optional[tk.Tk] = None,
                 on_save: Optional[Callable] = None):
        self.db = database
        self.project_mapper = project_mapper
        self.parent = parent
        self.on_save = on_save
        self.window: Optional[tk.Toplevel] = None
        self._selected_mapping_id: Optional[int] = None

    def show(self):
        """Show the mappings window."""
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
        """Create the mappings window."""
        if self.parent:
            self.window = Toplevel(self.parent)
        else:
            if TTKBOOTSTRAP_AVAILABLE:
                from ttkbootstrap import Window
                self.window = Window(themename="darkly")
            else:
                self.window = tk.Toplevel()

        self.window.title("ActivityMonitor - Project Mappings")
        self.window.geometry("700x500")
        self.window.resizable(True, True)

        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Main container
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Description
        desc_label = ttk.Label(
            main_frame,
            text="Define custom display names for projects. Mappings are applied in priority order.",
            font=('Segoe UI', 9),
            foreground='#888'
        )
        desc_label.pack(anchor='w', pady=(0, 10))

        # Create list section
        self._create_list_section(main_frame)

        # Create form section
        self._create_form_section(main_frame)

        # Create buttons
        self._create_buttons(main_frame)

    def _create_list_section(self, parent):
        """Create the mappings list."""
        list_frame = ttk.LabelFrame(parent, text="Mappings")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Treeview
        columns = ('type', 'match', 'display', 'priority', 'enabled')
        self._tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=8)

        self._tree.heading('type', text='Match Type')
        self._tree.heading('match', text='Match Value')
        self._tree.heading('display', text='Display Name')
        self._tree.heading('priority', text='Priority')
        self._tree.heading('enabled', text='Enabled')

        self._tree.column('type', width=100, minwidth=80)
        self._tree.column('match', width=180, minwidth=120)
        self._tree.column('display', width=180, minwidth=120)
        self._tree.column('priority', width=60, minwidth=50, anchor='center')
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
        form_frame = ttk.LabelFrame(parent, text="Add / Edit Mapping")
        form_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Match Type and Match Value
        row1 = ttk.Frame(form_frame)
        row1.pack(fill=tk.X, pady=5, padx=10)

        ttk.Label(row1, text="Match Type:", width=12, anchor='w').pack(side=tk.LEFT)
        self._type_var = tk.StringVar(value='project')
        type_combo = ttk.Combobox(
            row1,
            textvariable=self._type_var,
            values=list(self.MATCH_TYPES.values()),
            state='readonly',
            width=15
        )
        type_combo.pack(side=tk.LEFT, padx=(0, 20))
        type_combo.current(1)  # Default to 'Project Name'

        ttk.Label(row1, text="Match Value:", width=12, anchor='w').pack(side=tk.LEFT)
        self._match_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._match_var, width=30).pack(side=tk.LEFT)

        # Row 2: Display Name and Priority
        row2 = ttk.Frame(form_frame)
        row2.pack(fill=tk.X, pady=5, padx=10)

        ttk.Label(row2, text="Display Name:", width=12, anchor='w').pack(side=tk.LEFT)
        self._display_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self._display_var, width=20).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(row2, text="Priority:", width=12, anchor='w').pack(side=tk.LEFT)
        self._priority_var = tk.StringVar(value='5')
        priority_spin = ttk.Spinbox(row2, from_=1, to=10, textvariable=self._priority_var, width=5)
        priority_spin.pack(side=tk.LEFT, padx=(0, 20))

        self._enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="Enabled", variable=self._enabled_var).pack(side=tk.LEFT)

        # Row 3: Action buttons
        row3 = ttk.Frame(form_frame)
        row3.pack(fill=tk.X, pady=(5, 10), padx=10)

        self._add_btn = ttk.Button(row3, text="➕ Add", command=self._add_mapping, width=10)
        self._add_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._update_btn = ttk.Button(row3, text="✏️ Update", command=self._update_mapping, width=10, state='disabled')
        self._update_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._delete_btn = ttk.Button(row3, text="🗑️ Delete", command=self._delete_mapping, width=10, state='disabled')
        self._delete_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(row3, text="Clear Form", command=self._clear_form, width=10).pack(side=tk.LEFT)

        # Help text
        help_text = ttk.Label(
            form_frame,
            text="Examples: Match 'devenv.exe' (Process) → 'Visual Studio', or 'MyProject123' (Project) → 'My Project'",
            font=('Segoe UI', 8),
            foreground='#666'
        )
        help_text.pack(anchor='w', padx=10, pady=(0, 5))

    def _create_buttons(self, parent):
        """Create bottom buttons."""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Close", command=self.close).pack(side=tk.RIGHT)

    def _refresh_list(self):
        """Refresh the mappings list."""
        # Clear existing items
        for item in self._tree.get_children():
            self._tree.delete(item)

        # Load mappings from database
        mappings = self.db.get_mappings()

        for mapping in mappings:
            match_type_display = self.MATCH_TYPES.get(mapping['match_type'], mapping['match_type'])
            enabled_display = '✓' if mapping['enabled'] else '✗'

            self._tree.insert('', tk.END,
                iid=str(mapping['id']),
                values=(
                    match_type_display,
                    mapping['match_value'],
                    mapping['display_name'],
                    mapping['priority'],
                    enabled_display
                )
            )

    def _on_select(self, event):
        """Handle selection in the list."""
        selection = self._tree.selection()
        if selection:
            self._selected_mapping_id = int(selection[0])
            self._load_mapping_to_form(self._selected_mapping_id)
            self._update_btn.config(state='normal')
            self._delete_btn.config(state='normal')
        else:
            self._selected_mapping_id = None
            self._update_btn.config(state='disabled')
            self._delete_btn.config(state='disabled')

    def _on_double_click(self, event):
        """Handle double-click to edit."""
        self._on_select(event)

    def _load_mapping_to_form(self, mapping_id: int):
        """Load a mapping into the form for editing."""
        mappings = self.db.get_mappings()
        for mapping in mappings:
            if mapping['id'] == mapping_id:
                # Set match type
                type_display = self.MATCH_TYPES.get(mapping['match_type'], 'Project Name')
                self._type_var.set(type_display)

                self._match_var.set(mapping['match_value'])
                self._display_var.set(mapping['display_name'])
                self._priority_var.set(str(mapping['priority']))
                self._enabled_var.set(mapping['enabled'])
                break

    def _get_match_type_key(self) -> str:
        """Convert display match type to database key."""
        display_value = self._type_var.get()
        for key, value in self.MATCH_TYPES.items():
            if value == display_value:
                return key
        return 'project'

    def _add_mapping(self):
        """Add a new mapping."""
        match_type = self._get_match_type_key()
        match_value = self._match_var.get().strip()
        display_name = self._display_var.get().strip()
        priority = int(self._priority_var.get())
        enabled = self._enabled_var.get()

        if not match_value or not display_name:
            self._show_error("Validation Error", "Match Value and Display Name are required.")
            return

        try:
            self.db.add_mapping(match_type, match_value, display_name, priority, enabled)
            self._refresh_list()
            self._clear_form()
            self._notify_change()
            self._show_info("Success", f"Mapping added: '{match_value}' → '{display_name}'")
        except Exception as e:
            self._show_error("Error", f"Failed to add mapping: {e}")

    def _update_mapping(self):
        """Update the selected mapping."""
        if self._selected_mapping_id is None:
            return

        match_type = self._get_match_type_key()
        match_value = self._match_var.get().strip()
        display_name = self._display_var.get().strip()
        priority = int(self._priority_var.get())
        enabled = self._enabled_var.get()

        if not match_value or not display_name:
            self._show_error("Validation Error", "Match Value and Display Name are required.")
            return

        try:
            self.db.update_mapping(
                self._selected_mapping_id,
                match_type=match_type,
                match_value=match_value,
                display_name=display_name,
                priority=priority,
                enabled=enabled
            )
            self._refresh_list()
            self._clear_form()
            self._notify_change()
            self._show_info("Success", "Mapping updated successfully.")
        except Exception as e:
            self._show_error("Error", f"Failed to update mapping: {e}")

    def _delete_mapping(self):
        """Delete the selected mapping."""
        if self._selected_mapping_id is None:
            return

        if not self._show_yesno("Confirm Delete", "Are you sure you want to delete this mapping?"):
            return

        try:
            self.db.delete_mapping(self._selected_mapping_id)
            self._refresh_list()
            self._clear_form()
            self._notify_change()
        except Exception as e:
            self._show_error("Error", f"Failed to delete mapping: {e}")

    def _clear_form(self):
        """Clear the form fields."""
        self._type_var.set('Project Name')
        self._match_var.set('')
        self._display_var.set('')
        self._priority_var.set('5')
        self._enabled_var.set(True)
        self._selected_mapping_id = None
        self._update_btn.config(state='disabled')
        self._delete_btn.config(state='disabled')

        # Clear selection in tree
        for item in self._tree.selection():
            self._tree.selection_remove(item)

    def _notify_change(self):
        """Notify that mappings have changed."""
        # Reload mappings in the project mapper
        if self.project_mapper:
            self.project_mapper.reload_mappings()

        # Call the on_save callback if provided
        if self.on_save:
            self.on_save()

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
