import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import datetime
import os
import webbrowser
import sqlite3

# Optional imports for extra features
try:
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    # ICS support
    from icalendar import Calendar, Event
except ImportError:
    Calendar = None
    Event = None

try:
    # For desktop notifications (Windows/others)
    from plyer import notification
except ImportError:
    notification = None


# =================================================================
#                          DATA / MODEL
# =================================================================

class ArcanaeumDB:
    """
    The ArcanaeumDB handles creating and managing the underlying SQLite database.
    It has tables for:
      - tasks        (the main schedule items)
      - phases       (learning phases, each can have multiple tasks)
      - objectives   (each objective belongs to a phase; tasks can reference an objective)
      - reflections  (daily or ad-hoc reflection logs)
    """

    def __init__(self, db_file='arcanaeum.db'):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        # Create tasks table
        c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phase_id INTEGER,
            objective_id INTEGER,
            title TEXT,
            description TEXT,
            date TEXT,
            status TEXT,
            resources TEXT,
            recurring INTEGER,
            priority TEXT,
            category TEXT,
            estimated_time TEXT,
            completion_timestamp TEXT,
            FOREIGN KEY (phase_id) REFERENCES phases (id),
            FOREIGN KEY (objective_id) REFERENCES objectives (id)
        )
        ''')

        # Create phases table
        c.execute('''
        CREATE TABLE IF NOT EXISTS phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phase_number INTEGER,
            phase_title TEXT,
            phase_description TEXT
        )
        ''')

        # Create objectives table
        c.execute('''
        CREATE TABLE IF NOT EXISTS objectives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phase_id INTEGER,
            objective_name TEXT,
            objective_description TEXT,
            completion_criteria TEXT,
            FOREIGN KEY (phase_id) REFERENCES phases (id)
        )
        ''')

        # Create reflections table
        c.execute('''
        CREATE TABLE IF NOT EXISTS reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            content TEXT
        )
        ''')

        conn.commit()
        conn.close()

    # -----------------------------
    #         PHASES
    # -----------------------------
    def add_phase(self, phase):
        """
        phase = {
           'phase_number': int,
           'phase_title': str,
           'phase_description': str
        }
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''INSERT INTO phases (phase_number, phase_title, phase_description)
                     VALUES (?, ?, ?)''',
                  (phase['phase_number'], phase['phase_title'], phase['phase_description']))
        conn.commit()
        conn.close()

    def get_phases(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            SELECT id, phase_number, phase_title, phase_description
            FROM phases ORDER BY phase_number
        ''')
        rows = c.fetchall()
        conn.close()
        phases = []
        for r in rows:
            phases.append({
                'id': r[0],
                'phase_number': r[1],
                'phase_title': r[2],
                'phase_description': r[3]
            })
        return phases

    def update_phase(self, phase_id, phase):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            UPDATE phases
            SET phase_number=?, phase_title=?, phase_description=?
            WHERE id=?
        ''',
                  (phase['phase_number'], phase['phase_title'], phase['phase_description'], phase_id))
        conn.commit()
        conn.close()

    def delete_phase(self, phase_id):
        """
        Deleting a phase sets phase_id = NULL for tasks and objectives referencing it
        (or you could delete them, but let's keep them accessible).
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        # Nullify tasks
        c.execute('UPDATE tasks SET phase_id=NULL, objective_id=NULL WHERE phase_id=?', (phase_id,))
        # Nullify objectives
        c.execute('UPDATE objectives SET phase_id=NULL WHERE phase_id=?', (phase_id,))
        # Delete the phase itself
        c.execute('DELETE FROM phases WHERE id=?', (phase_id,))
        conn.commit()
        conn.close()

    # -----------------------------
    #         OBJECTIVES
    # -----------------------------
    def add_objective(self, objective):
        """
        objective = {
          'phase_id': int,
          'objective_name': str,
          'objective_description': str,
          'completion_criteria': str
        }
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            INSERT INTO objectives (phase_id, objective_name, objective_description, completion_criteria)
            VALUES (?, ?, ?, ?)
        ''', (objective['phase_id'], objective['objective_name'],
              objective['objective_description'], objective.get('completion_criteria', '')))
        conn.commit()
        conn.close()

    def get_objectives(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            SELECT id, phase_id, objective_name, objective_description, completion_criteria
            FROM objectives
        ''')
        rows = c.fetchall()
        conn.close()
        objs = []
        for r in rows:
            objs.append({
                'id': r[0],
                'phase_id': r[1],
                'objective_name': r[2],
                'objective_description': r[3],
                'completion_criteria': r[4]
            })
        return objs

    def update_objective(self, objective_id, objective):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            UPDATE objectives
            SET phase_id=?, objective_name=?, objective_description=?, completion_criteria=?
            WHERE id=?
        ''',
                  (objective['phase_id'], objective['objective_name'],
                   objective['objective_description'], objective.get('completion_criteria', ''),
                   objective_id))
        conn.commit()
        conn.close()

    def delete_objective(self, objective_id):
        """
        Deleting an objective sets objective_id=NULL for tasks referencing it,
        then removes the objective entry.
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('UPDATE tasks SET objective_id=NULL WHERE objective_id=?', (objective_id,))
        c.execute('DELETE FROM objectives WHERE id=?', (objective_id,))
        conn.commit()
        conn.close()

    # -----------------------------
    #         TASKS
    # -----------------------------
    def add_task(self, task):
        """
        task = {
            'phase_id': ...,
            'objective_id': ...,
            'title': ...,
            'description': ...,
            'date': ...,
            'status': ...,
            'resources': [...],
            'recurring': bool,
            'priority': ...,
            'category': ...,
            'estimated_time': ...,
            'completion_timestamp': ...
        }
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            INSERT INTO tasks (
                phase_id, objective_id, title, description, date, status, resources, recurring,
                priority, category, estimated_time, completion_timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
                  (task.get('phase_id', None),
                   task.get('objective_id', None),
                   task['title'],
                   task['description'],
                   task['date'],
                   task['status'],
                   ','.join(task.get('resources', [])),
                   1 if task.get('recurring', False) else 0,
                   task.get('priority', 'Medium'),
                   task.get('category', 'General'),
                   task.get('estimated_time', ''),
                   task.get('completion_timestamp', '')
                  ))
        conn.commit()
        conn.close()

    def get_tasks(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            SELECT
                id, phase_id, objective_id, title, description, date, status, resources,
                recurring, priority, category, estimated_time, completion_timestamp
            FROM tasks
        ''')
        rows = c.fetchall()
        conn.close()
        tasks = []
        for r in rows:
            tasks.append({
                'id': r[0],
                'phase_id': r[1],
                'objective_id': r[2],
                'title': r[3],
                'description': r[4],
                'date': r[5],
                'status': r[6],
                'resources': r[7].split(',') if r[7] else [],
                'recurring': bool(r[8]),
                'priority': r[9],
                'category': r[10],
                'estimated_time': r[11],
                'completion_timestamp': r[12]
            })
        return tasks

    def get_task_by_id(self, task_id):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            SELECT
                id, phase_id, objective_id, title, description, date, status, resources,
                recurring, priority, category, estimated_time, completion_timestamp
            FROM tasks
            WHERE id=?
        ''', (task_id,))
        r = c.fetchone()
        conn.close()
        if r:
            return {
                'id': r[0],
                'phase_id': r[1],
                'objective_id': r[2],
                'title': r[3],
                'description': r[4],
                'date': r[5],
                'status': r[6],
                'resources': r[7].split(',') if r[7] else [],
                'recurring': bool(r[8]),
                'priority': r[9],
                'category': r[10],
                'estimated_time': r[11],
                'completion_timestamp': r[12]
            }
        return None

    def update_task(self, task_id, task):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''
            UPDATE tasks
            SET phase_id=?, objective_id=?, title=?, description=?, date=?, status=?, resources=?,
                recurring=?, priority=?, category=?, estimated_time=?, completion_timestamp=?
            WHERE id=?
        ''',
                  (task.get('phase_id', None),
                   task.get('objective_id', None),
                   task['title'],
                   task['description'],
                   task['date'],
                   task['status'],
                   ','.join(task.get('resources', [])),
                   1 if task.get('recurring', False) else 0,
                   task.get('priority', 'Medium'),
                   task.get('category', 'General'),
                   task.get('estimated_time', ''),
                   task.get('completion_timestamp', ''),
                   task_id))
        conn.commit()
        conn.close()

    def delete_task(self, task_id):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        conn.commit()
        conn.close()

    # -----------------------------
    #       REFLECTIONS
    # -----------------------------
    def add_reflection(self, content):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('INSERT INTO reflections (timestamp, content) VALUES (?, ?)', (timestamp, content))
        conn.commit()
        conn.close()

    def get_reflections(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT id, timestamp, content FROM reflections ORDER BY id DESC')
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            result.append({
                'id': r[0],
                'timestamp': r[1],
                'content': r[2]
            })
        return result

    def delete_reflection(self, reflection_id):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('DELETE FROM reflections WHERE id=?', (reflection_id,))
        conn.commit()
        conn.close()


# =================================================================
#                      MAIN APPLICATION
# =================================================================

class Arcanaeum(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Arcanaeum - The Personal Learning Navigator")
        self.geometry("1400x750")

        # DB/Model
        self.db = ArcanaeumDB()

        # Style
        self.style = ttk.Style(self)
        self.style.theme_use('clam')

        # Filtered tasks in UI
        self.filtered_tasks = []

        # Create UI
        self._create_menu()
        self._create_search_filters()
        self._create_treeview()
        self._create_progress()
        self._create_buttons()
        self.populate_tasks()

        # Weekly auto-check
        self.check_for_weekly_wrapup()

        # Optional notifications for tasks due today
        self.notify_tasks_due_today()

    # ----------------------------------------------------------
    #                   MENU BAR
    # ----------------------------------------------------------
    def _create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import JSON", command=self.import_json)
        file_menu.add_command(label="Export JSON", command=self.export_json)
        if Calendar and Event:
            file_menu.add_command(label="Import ICS", command=self.import_ics)
            file_menu.add_command(label="Export ICS", command=self.export_ics)
        file_menu.add_command(label="Export CSV", command=self.export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Calendar View", command=self.show_calendar)
        view_menu.add_command(label="Kanban Board", command=self.show_kanban_board)
        view_menu.add_command(label="Statistics", command=self.show_statistics)
        view_menu.add_command(label="Toggle Dark Mode", command=self.toggle_dark_mode)

        # Phases Menu
        phases_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Phases", menu=phases_menu)
        phases_menu.add_command(label="Manage Phases", command=self.manage_phases)

        # Objectives Menu
        objectives_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Objectives", menu=objectives_menu)
        objectives_menu.add_command(label="Manage Objectives", command=self.manage_objectives)

        # Reflections Menu
        reflections_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Reflections", menu=reflections_menu)
        reflections_menu.add_command(label="Add Reflection", command=self.add_reflection_dialog)
        reflections_menu.add_command(label="View Reflections", command=self.view_reflections)

        # Tools Menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Weekly Report", command=self.show_weekly_report)
        tools_menu.add_command(label="Focus Lock (Stub)", command=self.toggle_focus_lock)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    # ----------------------------------------------------------
    #                   SEARCH & FILTERS
    # ----------------------------------------------------------
    def _create_search_filters(self):
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<KeyRelease>", self.on_search)
        ttk.Button(search_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=5)

        # Category Filter
        ttk.Label(search_frame, text="Category Filter:").pack(side=tk.LEFT, padx=5)
        self.category_filter_var = tk.StringVar(value="All")
        self.category_filter = ttk.Combobox(
            search_frame, textvariable=self.category_filter_var,
            values=["All", "Work", "Personal", "Study", "General"]
        )
        self.category_filter.pack(side=tk.LEFT)
        self.category_filter.bind("<<ComboboxSelected>>", lambda e: self.populate_tasks())

        # Priority Filter
        ttk.Label(search_frame, text="Priority Filter:").pack(side=tk.LEFT, padx=5)
        self.priority_filter_var = tk.StringVar(value="All")
        self.priority_filter = ttk.Combobox(
            search_frame, textvariable=self.priority_filter_var,
            values=["All", "Low", "Medium", "High", "Critical"]
        )
        self.priority_filter.pack(side=tk.LEFT)
        self.priority_filter.bind("<<ComboboxSelected>>", lambda e: self.populate_tasks())

        # Phase Filter
        ttk.Label(search_frame, text="Phase Filter:").pack(side=tk.LEFT, padx=5)
        self.phase_filter_var = tk.StringVar(value="All")
        self.phase_filter = ttk.Combobox(search_frame, textvariable=self.phase_filter_var)
        self.phase_filter.pack(side=tk.LEFT)
        self.phase_filter.bind("<<ComboboxSelected>>", lambda e: self.populate_tasks())

        # Objective Filter
        ttk.Label(search_frame, text="Objective Filter:").pack(side=tk.LEFT, padx=5)
        self.objective_filter_var = tk.StringVar(value="All")
        self.objective_filter = ttk.Combobox(search_frame, textvariable=self.objective_filter_var)
        self.objective_filter.pack(side=tk.LEFT)
        self.objective_filter.bind("<<ComboboxSelected>>", lambda e: self.populate_tasks())

    # ----------------------------------------------------------
    #                   TREEVIEW
    # ----------------------------------------------------------
    def _create_treeview(self):
        columns = ("Title", "Date", "Status", "Category", "Priority", "Est Time", "Phase", "Objective")
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=20)
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_by(c, False))
            self.tree.column(col, anchor=tk.CENTER, width=150)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<Double-1>', self.on_task_select)

    # ----------------------------------------------------------
    #                   PROGRESS BAR
    # ----------------------------------------------------------
    def _create_progress(self):
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(progress_frame, text="Overall Progress:").pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    # ----------------------------------------------------------
    #                   BUTTONS
    # ----------------------------------------------------------
    def _create_buttons(self):
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Add Task", command=self.add_task_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Edit Task", command=self.edit_task_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete Task", command=self.delete_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Mark as Completed", command=self.mark_completed).pack(side=tk.LEFT, padx=5)

        # Quick Add
        self.quick_add_var = tk.StringVar()
        ttk.Label(btn_frame, text="Quick Add:").pack(side=tk.LEFT, padx=5)
        quick_add_entry = ttk.Entry(btn_frame, textvariable=self.quick_add_var, width=60)
        quick_add_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        quick_add_entry.bind("<Return>", self.quick_add_task)

    # ----------------------------------------------------------
    #               POPULATING & SEARCH
    # ----------------------------------------------------------
    def populate_tasks(self):
        self.tree.delete(*self.tree.get_children())

        phases = self.db.get_phases()
        objectives = self.db.get_objectives()
        tasks = self.db.get_tasks()

        # Build phase map
        phase_map = {p['id']: f"{p['phase_number']}: {p['phase_title']}" for p in phases}
        # Build objective map
        objective_map = {}
        for o in objectives:
            # e.g. "3|Backprop Fundamentals"
            objective_map[o['id']] = f"{o['id']} - {o['objective_name']}"

        # Rebuild combo values for phase & objective
        phase_names = ["All"] + [f"{p['phase_number']}: {p['phase_title']}" for p in phases]
        current_phase_filter_val = self.phase_filter_var.get()
        self.phase_filter['values'] = phase_names
        if current_phase_filter_val not in phase_names:
            self.phase_filter_var.set("All")

        objective_names = ["All"] + [f"{o['id']} - {o['objective_name']}" for o in objectives]
        current_obj_filter_val = self.objective_filter_var.get()
        self.objective_filter['values'] = objective_names
        if current_obj_filter_val not in objective_names:
            self.objective_filter_var.set("All")

        # Date-based status check
        today = datetime.date.today()
        for t in tasks:
            if t['status'] == 'Pending':
                try:
                    dt = datetime.datetime.strptime(t['date'], '%Y-%m-%d').date()
                    if dt < today:
                        t['status'] = 'Behind'
                    elif dt > today:
                        t['status'] = 'Ahead'
                    else:
                        t['status'] = 'Pending'
                    self.db.update_task(t['id'], t)
                except:
                    pass

        # Apply filters
        query = self.search_var.get().lower()
        cat_filter = self.category_filter_var.get()
        pri_filter = self.priority_filter_var.get()
        phase_filter_value = self.phase_filter_var.get()
        obj_filter_value = self.objective_filter_var.get()

        filtered = []
        for t in tasks:
            # Search filter
            if query:
                if query not in t['title'].lower() and query not in t['description'].lower():
                    continue
            # Category filter
            if cat_filter != "All" and t['category'] != cat_filter:
                continue
            # Priority filter
            if pri_filter != "All" and t['priority'] != pri_filter:
                continue

            # Phase filter
            ph_label = phase_map.get(t['phase_id'], "No Phase")
            if phase_filter_value != "All" and phase_filter_value != ph_label:
                continue

            # Objective filter
            obj_label = "No Objective"
            if t['objective_id']:
                obj_label = objective_map.get(t['objective_id'], "No Objective")
            if obj_filter_value != "All" and obj_filter_value != obj_label:
                continue

            filtered.append(t)

        self.filtered_tasks = filtered

        # Insert into tree
        for t in filtered:
            ph_label = phase_map.get(t['phase_id'], "No Phase")
            obj_label = "No Objective"
            if t['objective_id']:
                obj_label = objective_map.get(t['objective_id'], "No Objective")

            self.tree.insert(
                '', tk.END, iid=str(t['id']),
                values=(
                    t['title'],
                    t['date'],
                    t['status'],
                    t['category'],
                    t['priority'],
                    t['estimated_time'],
                    ph_label,
                    obj_label
                )
            )

        self.update_progress()

    def on_search(self, event):
        self.populate_tasks()

    def clear_search(self):
        self.search_var.set('')
        self.populate_tasks()

    # ----------------------------------------------------------
    #               SORTING & PROGRESS
    # ----------------------------------------------------------
    def sort_by(self, col, descending):
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]

        def try_float(x):
            try:
                return float(x)
            except:
                return x

        data.sort(key=lambda x: try_float(x[0]), reverse=descending)
        for idx, item in enumerate(data):
            self.tree.move(item[1], '', idx)

        self.tree.heading(col, command=lambda: self.sort_by(col, not descending))

    def update_progress(self):
        tasks = self.db.get_tasks()
        total_tasks = len(tasks)
        if total_tasks == 0:
            progress = 0
        else:
            completed = len([t for t in tasks if t['status'] == 'Completed'])
            progress = (completed / total_tasks) * 100
        self.progress_var.set(progress)

    # ----------------------------------------------------------
    #               TASK CRUD
    # ----------------------------------------------------------
    def add_task_dialog(self):
        TaskDialog(self, self.db, self.populate_tasks)

    def edit_task_dialog(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Select a task to edit.")
            return
        task_id = int(selected_item[0])
        task = self.db.get_task_by_id(task_id)
        if task:
            TaskDialog(self, self.db, self.populate_tasks, task=task)

    def delete_task(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Select a task to delete.")
            return
        task_id = int(selected_item[0])
        self.db.delete_task(task_id)
        self.populate_tasks()

    def mark_completed(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Select a task to mark completed.")
            return
        task_id = int(selected_item[0])
        task = self.db.get_task_by_id(task_id)
        if task:
            task['status'] = 'Completed'
            task['completion_timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # If recurring, re-schedule
            if task.get('recurring'):
                try:
                    old_date = datetime.datetime.strptime(task['date'], '%Y-%m-%d').date()
                    new_date = old_date + datetime.timedelta(days=7)
                    task['date'] = new_date.strftime('%Y-%m-%d')
                    task['status'] = 'Pending'
                    task['completion_timestamp'] = ''
                except:
                    pass
            self.db.update_task(task_id, task)
        self.populate_tasks()

    def quick_add_task(self, event):
        text = self.quick_add_var.get().strip()
        if not text:
            return
        import re
        date_match = re.search(r'\bby\s(\d{4}-\d{2}-\d{2})\b', text)
        date_str = date_match.group(1) if date_match else datetime.datetime.now().strftime('%Y-%m-%d')
        priority_match = re.search(r'\bpriority:(\w+)\b', text, re.IGNORECASE)
        priority = priority_match.group(1).capitalize() if priority_match else 'Medium'
        category_match = re.search(r'\bcategory:(\w+)\b', text, re.IGNORECASE)
        category = category_match.group(1).capitalize() if category_match else 'General'

        # Title is what's left
        title = text
        if 'by ' in title:
            title = title.split('by ')[0].strip()
        import re
        title = re.sub(r'priority:\w+', '', title, flags=re.IGNORECASE)
        title = re.sub(r'category:\w+', '', title, flags=re.IGNORECASE)
        title = title.strip()

        task = {
            'phase_id': None,
            'objective_id': None,
            'title': title,
            'description': '',
            'date': date_str,
            'status': 'Pending',
            'resources': [],
            'recurring': False,
            'priority': priority,
            'category': category,
            'estimated_time': '',
            'completion_timestamp': ''
        }
        self.db.add_task(task)
        self.quick_add_var.set('')
        self.populate_tasks()

    def on_task_select(self, event):
        sel = self.tree.selection()
        if sel:
            task_id = int(sel[0])
            task = self.db.get_task_by_id(task_id)
            if task:
                TaskDetailDialog(self, task)

    # ----------------------------------------------------------
    #               JSON IMPORT/EXPORT
    # ----------------------------------------------------------
    def import_json(self):
        """
        Currently expects a JSON of the form:
          {
            "tasks": [ { ...task fields... }, ... ],
            "phases": [ { ...phase fields... }, ... ],
            "objectives": [ { ...objective fields... }, ... ]
          }
        We do not handle partial or missing arrays gracefully here—just a quick approach.
        """
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not filename:
            return
        with open(filename, 'r') as f:
            data = json.load(f)

        confirm = messagebox.askyesno("Confirm Import", "This will replace all current tasks, phases, objectives. Continue?")
        if confirm:
            # Wipe tasks, phases, objectives
            conn = sqlite3.connect(self.db.db_file)
            c = conn.cursor()
            c.execute('DELETE FROM tasks')
            c.execute('DELETE FROM phases')
            c.execute('DELETE FROM objectives')
            conn.commit()
            conn.close()

            # Re-add phases
            for p in data.get('phases', []):
                self.db.add_phase(p)
            # Re-add objectives
            for o in data.get('objectives', []):
                self.db.add_objective(o)
            # Re-add tasks
            for t in data.get('tasks', []):
                self.db.add_task(t)

            self.populate_tasks()
            messagebox.showinfo("Import Successful", f"Imported from {filename}")

    def export_json(self):
        tasks = self.db.get_tasks()
        phases = self.db.get_phases()
        objectives = self.db.get_objectives()
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not filename:
            return
        with open(filename, 'w') as f:
            json.dump({
                "tasks": tasks,
                "phases": phases,
                "objectives": objectives
            }, f, indent=4)
        messagebox.showinfo("Export Successful", f"Exported to {filename}")

    def export_csv(self):
        tasks = self.db.get_tasks()
        if not tasks:
            messagebox.showinfo("No Tasks", "No tasks to export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not filename:
            return
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=tasks[0].keys())
            writer.writeheader()
            for t in tasks:
                writer.writerow(t)
        messagebox.showinfo("Export Successful", f"Tasks exported to {filename}")

    def import_ics(self):
        if not Calendar:
            messagebox.showwarning("Not Available", "icalendar library not installed.")
            return
        filename = filedialog.askopenfilename(filetypes=[("ICS files", "*.ics")])
        if not filename:
            return
        with open(filename, 'rb') as f:
            cal_data = f.read()
        cal = Calendar.from_ical(cal_data)

        confirm = messagebox.askyesno("Confirm Import", "This will replace all current tasks. Continue?")
        if confirm:
            conn = sqlite3.connect(self.db.db_file)
            c = conn.cursor()
            c.execute('DELETE FROM tasks')
            conn.commit()
            conn.close()

            for component in cal.walk('vevent'):
                title = str(component.get('summary', 'No Title'))
                description = str(component.get('description', ''))
                dtstart = component.get('dtstart')
                date_str = (dtstart.dt.strftime('%Y-%m-%d') if dtstart else
                            datetime.datetime.now().strftime('%Y-%m-%d'))
                task = {
                    'phase_id': None,
                    'objective_id': None,
                    'title': title,
                    'description': description,
                    'date': date_str,
                    'status': 'Pending',
                    'resources': [],
                    'recurring': False,
                    'priority': 'Medium',
                    'category': 'General',
                    'estimated_time': '',
                    'completion_timestamp': ''
                }
                self.db.add_task(task)

        self.populate_tasks()
        messagebox.showinfo("Import Successful", "Imported from ICS file.")

    def export_ics(self):
        if not Calendar:
            messagebox.showwarning("Not Available", "icalendar library not installed.")
            return
        tasks = self.db.get_tasks()
        cal = Calendar()
        cal.add('prodid', '-//Arcanaeum//')
        cal.add('version', '2.0')
        for t in tasks:
            event = Event()
            event.add('summary', t['title'])
            event.add('description', t['description'])
            try:
                dt = datetime.datetime.strptime(t['date'], '%Y-%m-%d')
                event.add('dtstart', dt)
            except:
                pass
            cal.add_component(event)
        filename = filedialog.asksaveasfilename(defaultextension=".ics", filetypes=[("ICS files", "*.ics")])
        if not filename:
            return
        with open(filename, 'wb') as f:
            f.write(cal.to_ical())
        messagebox.showinfo("Export Successful", f"Exported to {filename}")

    # ----------------------------------------------------------
    #               VIEWS: CALENDAR, KANBAN, STATS
    # ----------------------------------------------------------
    def show_calendar(self):
        CalendarView(self, self.db.get_tasks())

    def show_kanban_board(self):
        KanbanBoard(self, self.db.get_tasks())

    def show_statistics(self):
        if plt is None:
            messagebox.showwarning("Not Available", "matplotlib not installed.")
            return
        StatsView(self, self.db.get_tasks())

    # ----------------------------------------------------------
    #               DARK MODE
    # ----------------------------------------------------------
    def toggle_dark_mode(self):
        current_theme = self.style.theme_use()
        if current_theme == 'clam':
            self.style.theme_use('alt')
        else:
            self.style.theme_use('clam')

    # ----------------------------------------------------------
    #               PHASES MANAGEMENT
    # ----------------------------------------------------------
    def manage_phases(self):
        PhaseManagerDialog(self, self.db, self.populate_tasks)

    # ----------------------------------------------------------
    #               OBJECTIVES MANAGEMENT
    # ----------------------------------------------------------
    def manage_objectives(self):
        ObjectiveManagerDialog(self, self.db, self.populate_tasks)

    # ----------------------------------------------------------
    #               REFLECTIONS
    # ----------------------------------------------------------
    def add_reflection_dialog(self):
        ReflectionDialog(self, self.db, self.populate_tasks)

    def view_reflections(self):
        ReflectionViewer(self, self.db)

    # ----------------------------------------------------------
    #               WEEKLY REPORT
    # ----------------------------------------------------------
    def show_weekly_report(self):
        WeeklyReport(self, self.db.get_tasks(), self.db.get_reflections())

    def check_for_weekly_wrapup(self):
        """
        Simple demonstration: once a week, prompt user if they'd like to do a weekly wrap-up.
        (You could store last-check date in DB or config. For brevity, we'll skip details.)
        """
        pass

    # ----------------------------------------------------------
    #               FOCUS LOCK (Stub)
    # ----------------------------------------------------------
    def toggle_focus_lock(self):
        response = messagebox.askyesno("Focus Lock", "Activate Focus Lock for 30 min? (Stub demonstration)")
        if response:
            messagebox.showinfo("Focus Lock", "Focus Lock activated. (Stub only, no real blocking.)")

    # ----------------------------------------------------------
    #               NOTIFICATIONS
    # ----------------------------------------------------------
    def notify_tasks_due_today(self):
        if not notification:
            return
        tasks = self.db.get_tasks()
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        due_today = [t for t in tasks if t['date'] == today and t['status'] in ['Pending', 'Behind', 'Ahead']]
        for t in due_today:
            notification.notify(
                title="Arcanaeum - Task Due Today",
                message=f"{t['title']} is scheduled for today!",
                timeout=5
            )

    # ----------------------------------------------------------
    #               ABOUT
    # ----------------------------------------------------------
    def show_about(self):
        messagebox.showinfo(
            "About Arcanaeum",
            "Arcanaeum: The Personal Learning Navigator\n"
            "Now supports objectives within phases for a milestone-based approach.\n"
            "Developed with love and autonomy!"
        )


# =================================================================
#                   TASK DIALOGS
# =================================================================

class TaskDialog(tk.Toplevel):
    def __init__(self, parent, db, refresh_callback, task=None):
        super().__init__(parent)
        self.db = db
        self.refresh_callback = refresh_callback
        self.task = task
        self.title("Task Details")
        self.geometry("500x750")
        self.create_widgets()
        if task:
            self.populate_fields()

    def create_widgets(self):
        # Grab phases/objectives
        phases = self.db.get_phases()
        objectives = self.db.get_objectives()

        phase_choices = ["(None)"] + [f"{p['id']}|{p['phase_number']} - {p['phase_title']}" for p in phases]
        objective_choices = ["(None)"] + [
            f"{o['id']}|{o['objective_name']}" for o in objectives
        ]

        # Phase
        ttk.Label(self, text="Phase:").pack(pady=5)
        self.phase_var = tk.StringVar()
        self.phase_combo = ttk.Combobox(self, textvariable=self.phase_var, values=phase_choices)
        self.phase_combo.pack()

        # Objective
        ttk.Label(self, text="Objective:").pack(pady=5)
        self.obj_var = tk.StringVar()
        self.obj_combo = ttk.Combobox(self, textvariable=self.obj_var, values=objective_choices)
        self.obj_combo.pack()

        ttk.Label(self, text="Title:").pack(pady=5)
        self.title_entry = ttk.Entry(self, width=50)
        self.title_entry.pack()

        ttk.Label(self, text="Description:").pack(pady=5)
        self.desc_text = tk.Text(self, width=50, height=5)
        self.desc_text.pack()

        ttk.Label(self, text="Date (YYYY-MM-DD):").pack(pady=5)
        self.date_entry = ttk.Entry(self, width=50)
        self.date_entry.pack()

        ttk.Label(self, text="Status:").pack(pady=5)
        self.status_var = tk.StringVar(value="Pending")
        status_options = ["Pending", "Completed", "Behind", "Ahead"]
        self.status_menu = ttk.OptionMenu(self, self.status_var, *status_options)
        self.status_menu.pack()

        ttk.Label(self, text="Priority:").pack(pady=5)
        self.priority_var = tk.StringVar(value="Medium")
        priority_options = ["Low", "Medium", "High", "Critical"]
        self.priority_menu = ttk.OptionMenu(self, self.priority_var, *priority_options)
        self.priority_menu.pack()

        ttk.Label(self, text="Category:").pack(pady=5)
        self.category_var = tk.StringVar(value="General")
        category_options = ["General", "Work", "Personal", "Study"]
        self.category_menu = ttk.OptionMenu(self, self.category_var, *category_options)
        self.category_menu.pack()

        ttk.Label(self, text="Estimated Time (e.g., '2h', '30m')").pack(pady=5)
        self.estimate_entry = ttk.Entry(self, width=50)
        self.estimate_entry.pack()

        ttk.Label(self, text="Resources (comma-separated URLs or file paths):").pack(pady=5)
        self.resources_entry = ttk.Entry(self, width=50)
        self.resources_entry.pack()

        ttk.Label(self, text="Recurring:").pack(pady=5)
        self.recurring_var = tk.BooleanVar()
        self.recurring_check = ttk.Checkbutton(self, text="Repeat Weekly", variable=self.recurring_var)
        self.recurring_check.pack()

        ttk.Button(self, text="Save", command=self.save_task).pack(pady=10)

    def populate_fields(self):
        phases = self.db.get_phases()
        objectives = self.db.get_objectives()

        # Phase
        if self.task['phase_id']:
            for p in phases:
                if p['id'] == self.task['phase_id']:
                    self.phase_var.set(f"{p['id']}|{p['phase_number']} - {p['phase_title']}")
                    break

        # Objective
        if self.task['objective_id']:
            for o in objectives:
                if o['id'] == self.task['objective_id']:
                    self.obj_var.set(f"{o['id']}|{o['objective_name']}")
                    break

        self.title_entry.insert(0, self.task['title'])
        self.desc_text.insert(tk.END, self.task['description'])
        self.date_entry.insert(0, self.task['date'])
        self.status_var.set(self.task['status'])
        self.priority_var.set(self.task.get('priority', 'Medium'))
        self.category_var.set(self.task.get('category', 'General'))
        self.estimate_entry.insert(0, self.task.get('estimated_time', ''))
        self.resources_entry.insert(0, ','.join(self.task['resources']))
        self.recurring_var.set(self.task.get('recurring', False))

    def save_task(self):
        title = self.title_entry.get().strip()
        description = self.desc_text.get("1.0", tk.END).strip()
        date = self.date_entry.get().strip()
        status = self.status_var.get()
        priority = self.priority_var.get()
        category = self.category_var.get()
        estimated_time = self.estimate_entry.get().strip()
        resources = [r.strip() for r in self.resources_entry.get().split(',') if r.strip()]
        recurring = self.recurring_var.get()

        if not title:
            messagebox.showwarning("Validation Error", "Title is required.")
            return
        try:
            datetime.datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            messagebox.showwarning("Date Error", "Invalid date format (YYYY-MM-DD).")
            return

        # Phase ID
        phase_id = None
        pv = self.phase_var.get()
        if pv and pv != "(None)":
            splitted = pv.split('|')
            if splitted:
                try:
                    phase_id = int(splitted[0])
                except:
                    phase_id = None

        # Objective ID
        objective_id = None
        ov = self.obj_var.get()
        if ov and ov != "(None)":
            splitted = ov.split('|')
            if splitted:
                try:
                    objective_id = int(splitted[0])
                except:
                    objective_id = None

        new_task = {
            'phase_id': phase_id,
            'objective_id': objective_id,
            'title': title,
            'description': description,
            'date': date,
            'status': status,
            'resources': resources,
            'recurring': recurring,
            'priority': priority,
            'category': category,
            'estimated_time': estimated_time,
            'completion_timestamp': self.task.get('completion_timestamp', '') if self.task else ''
        }

        if self.task:
            self.db.update_task(self.task['id'], new_task)
        else:
            self.db.add_task(new_task)

        self.refresh_callback()
        self.destroy()


class TaskDetailDialog(tk.Toplevel):
    def __init__(self, parent, task):
        super().__init__(parent)
        self.title(task['title'])
        self.geometry("500x600")
        self.task = task
        self.create_widgets()

    def create_widgets(self):
        ttk.Label(self, text=f"Title: {self.task['title']}", font=("Arial", 14)).pack(pady=5)
        ttk.Label(self, text=f"Date: {self.task['date']}").pack(pady=5)
        ttk.Label(self, text=f"Status: {self.task['status']}").pack(pady=5)
        ttk.Label(self, text=f"Priority: {self.task.get('priority','Medium')}").pack(pady=5)
        ttk.Label(self, text=f"Category: {self.task.get('category','General')}").pack(pady=5)
        if self.task.get('estimated_time'):
            ttk.Label(self, text=f"Estimated Time: {self.task['estimated_time']}").pack(pady=5)
        if self.task.get('completion_timestamp'):
            ttk.Label(self, text=f"Completed At: {self.task['completion_timestamp']}").pack(pady=5)

        ttk.Label(self, text="Description:").pack(pady=5)
        desc_frame = ttk.Frame(self)
        desc_frame.pack(fill=tk.BOTH, expand=True)
        desc_text = tk.Text(desc_frame, wrap=tk.WORD, height=5)
        desc_text.pack(fill=tk.BOTH, expand=True)
        desc_text.insert(tk.END, self.task['description'])
        desc_text.configure(state='disabled')

        if self.task['resources']:
            ttk.Label(self, text="Resources:").pack(pady=5)
            for res in self.task['resources']:
                link = ttk.Label(self, text=res, foreground="blue", cursor="hand2")
                link.pack()
                link.bind("<Button-1>", lambda e, url=res: self.open_link(url))

        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

    def open_link(self, url):
        if os.path.exists(url):
            os.startfile(url)
        else:
            webbrowser.open_new(url)


# =================================================================
#                   PHASE MANAGER
# =================================================================

class PhaseManagerDialog(tk.Toplevel):
    """
    UI for creating, updating, or deleting phases in the learning plan.
    """
    def __init__(self, parent, db, refresh_callback):
        super().__init__(parent)
        self.db = db
        self.refresh_callback = refresh_callback
        self.title("Manage Phases")
        self.geometry("600x400")

        self.tree = ttk.Treeview(self, columns=("Number", "Title", "Description"), show='headings')
        self.tree.heading("Number", text="Phase #")
        self.tree.heading("Title", text="Phase Title")
        self.tree.heading("Description", text="Description")
        self.tree.column("Number", width=60, anchor=tk.CENTER)
        self.tree.column("Title", width=150, anchor=tk.CENTER)
        self.tree.column("Description", width=300, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.edit_phase_dialog)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Add Phase", command=self.add_phase_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete Phase", command=self.delete_phase).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=self.close_dialog).pack(side=tk.RIGHT, padx=5)

        self.populate_phases()

    def populate_phases(self):
        self.tree.delete(*self.tree.get_children())
        phases = self.db.get_phases()
        for p in phases:
            self.tree.insert(
                '', tk.END,
                iid=str(p['id']),
                values=(p['phase_number'], p['phase_title'], p['phase_description'])
            )

    def add_phase_dialog(self):
        PhaseDialog(self, self.db, self.populate_phases)

    def edit_phase_dialog(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        phase_id = int(sel[0])
        phases = self.db.get_phases()
        phase_obj = None
        for p in phases:
            if p['id'] == phase_id:
                phase_obj = p
                break
        if phase_obj:
            PhaseDialog(self, self.db, self.populate_phases, phase=phase_obj)

    def delete_phase(self):
        sel = self.tree.selection()
        if not sel:
            return
        phase_id = int(sel[0])
        confirm = messagebox.askyesno("Confirm", "Deleting a phase will remove references from tasks/objectives. Continue?")
        if confirm:
            self.db.delete_phase(phase_id)
            self.populate_phases()
            self.refresh_callback()  # Refresh main tasks tree

    def close_dialog(self):
        self.refresh_callback()
        self.destroy()


class PhaseDialog(tk.Toplevel):
    """
    Allows creating or editing a single phase.
    """
    def __init__(self, parent, db, refresh_callback, phase=None):
        super().__init__(parent)
        self.db = db
        self.refresh_callback = refresh_callback
        self.phase = phase
        self.title("Phase Details")
        self.geometry("400x300")

        ttk.Label(self, text="Phase Number:").pack(pady=5)
        self.num_var = tk.StringVar()
        self.num_entry = ttk.Entry(self, textvariable=self.num_var)
        self.num_entry.pack()

        ttk.Label(self, text="Phase Title:").pack(pady=5)
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(self, textvariable=self.title_var, width=50)
        self.title_entry.pack()

        ttk.Label(self, text="Description:").pack(pady=5)
        self.desc_text = tk.Text(self, width=50, height=5)
        self.desc_text.pack()

        ttk.Button(self, text="Save", command=self.save_phase).pack(pady=10)

        if phase:
            self.populate_fields()

    def populate_fields(self):
        self.num_var.set(str(self.phase['phase_number']))
        self.title_var.set(self.phase['phase_title'])
        self.desc_text.insert(tk.END, self.phase['phase_description'])

    def save_phase(self):
        try:
            phase_number = int(self.num_var.get().strip())
        except ValueError:
            messagebox.showwarning("Validation Error", "Phase Number must be an integer.")
            return
        phase_title = self.title_var.get().strip()
        phase_description = self.desc_text.get("1.0", tk.END).strip()

        if not phase_title:
            messagebox.showwarning("Validation Error", "Phase Title is required.")
            return

        new_phase = {
            'phase_number': phase_number,
            'phase_title': phase_title,
            'phase_description': phase_description
        }

        if self.phase:
            self.db.update_phase(self.phase['id'], new_phase)
        else:
            self.db.add_phase(new_phase)

        self.refresh_callback()
        self.destroy()


# =================================================================
#                OBJECTIVE MANAGER
# =================================================================

class ObjectiveManagerDialog(tk.Toplevel):
    """
    UI for creating, updating, or deleting objectives in the learning plan.
    Each objective belongs to a Phase (phase_id).
    """
    def __init__(self, parent, db, refresh_callback):
        super().__init__(parent)
        self.db = db
        self.refresh_callback = refresh_callback
        self.title("Manage Objectives")
        self.geometry("800x400")

        self.tree = ttk.Treeview(self, columns=("PhaseID", "ObjectiveName", "Description", "Criteria"), show='headings')
        self.tree.heading("PhaseID", text="Phase ID")
        self.tree.heading("ObjectiveName", text="Objective Name")
        self.tree.heading("Description", text="Description")
        self.tree.heading("Criteria", text="Completion Criteria")
        self.tree.column("PhaseID", width=60, anchor=tk.CENTER)
        self.tree.column("ObjectiveName", width=150, anchor=tk.CENTER)
        self.tree.column("Description", width=200, anchor=tk.W)
        self.tree.column("Criteria", width=200, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.edit_objective_dialog)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Add Objective", command=self.add_objective_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete Objective", command=self.delete_objective).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=self.close_dialog).pack(side=tk.RIGHT, padx=5)

        self.populate_objectives()

    def populate_objectives(self):
        self.tree.delete(*self.tree.get_children())
        objectives = self.db.get_objectives()
        for o in objectives:
            self.tree.insert(
                '', tk.END,
                iid=str(o['id']),
                values=(o['phase_id'], o['objective_name'], o['objective_description'], o.get('completion_criteria',''))
            )

    def add_objective_dialog(self):
        ObjectiveDialog(self, self.db, self.populate_objectives)

    def edit_objective_dialog(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        obj_id = int(sel[0])
        objectives = self.db.get_objectives()
        obj_obj = None
        for o in objectives:
            if o['id'] == obj_id:
                obj_obj = o
                break
        if obj_obj:
            ObjectiveDialog(self, self.db, self.populate_objectives, objective=obj_obj)

    def delete_objective(self):
        sel = self.tree.selection()
        if not sel:
            return
        obj_id = int(sel[0])
        confirm = messagebox.askyesno("Confirm", "Deleting an objective will remove references from tasks. Continue?")
        if confirm:
            self.db.delete_objective(obj_id)
            self.populate_objectives()
            self.refresh_callback()

    def close_dialog(self):
        self.refresh_callback()
        self.destroy()


class ObjectiveDialog(tk.Toplevel):
    """
    Allows creating or editing a single objective.
    Each objective is tied to a specific phase_id.
    """
    def __init__(self, parent, db, refresh_callback, objective=None):
        super().__init__(parent)
        self.db = db
        self.refresh_callback = refresh_callback
        self.objective = objective
        self.title("Objective Details")
        self.geometry("500x400")

        phases = self.db.get_phases()
        phase_choices = [(None, "(None)")] + [(p['id'], f"{p['phase_number']}: {p['phase_title']}") for p in phases]

        ttk.Label(self, text="Phase:").pack(pady=5)
        self.phase_var = tk.StringVar()
        self.phase_combo = ttk.Combobox(self, textvariable=self.phase_var,
                                        values=[f"{pc[0]}|{pc[1]}" for pc in phase_choices])
        self.phase_combo.pack()

        ttk.Label(self, text="Objective Name:").pack(pady=5)
        self.obj_name_var = tk.StringVar()
        self.obj_name_entry = ttk.Entry(self, textvariable=self.obj_name_var, width=50)
        self.obj_name_entry.pack()

        ttk.Label(self, text="Description:").pack(pady=5)
        self.desc_text = tk.Text(self, width=50, height=3)
        self.desc_text.pack()

        ttk.Label(self, text="Completion Criteria (optional):").pack(pady=5)
        self.criteria_text = tk.Text(self, width=50, height=3)
        self.criteria_text.pack()

        ttk.Button(self, text="Save", command=self.save_objective).pack(pady=10)

        if objective:
            self.populate_fields(phase_choices)

    def populate_fields(self, phase_choices):
        # Phase
        if self.objective['phase_id'] is not None:
            for pc in phase_choices:
                if pc[0] == self.objective['phase_id']:
                    self.phase_var.set(f"{pc[0]}|{pc[1]}")
                    break

        self.obj_name_var.set(self.objective['objective_name'])
        self.desc_text.insert(tk.END, self.objective['objective_description'])
        if self.objective.get('completion_criteria'):
            self.criteria_text.insert(tk.END, self.objective['completion_criteria'])

    def save_objective(self):
        # Phase ID
        pv = self.phase_var.get()
        phase_id = None
        if pv and pv != "None|(None)":
            splitted = pv.split('|')
            if splitted:
                try:
                    phase_id = int(splitted[0])
                except:
                    phase_id = None

        objective_name = self.obj_name_var.get().strip()
        objective_description = self.desc_text.get("1.0", tk.END).strip()
        completion_criteria = self.criteria_text.get("1.0", tk.END).strip()

        if not objective_name:
            messagebox.showwarning("Validation Error", "Objective Name is required.")
            return

        new_obj = {
            'phase_id': phase_id,
            'objective_name': objective_name,
            'objective_description': objective_description,
            'completion_criteria': completion_criteria
        }

        if self.objective:
            self.db.update_objective(self.objective['id'], new_obj)
        else:
            self.db.add_objective(new_obj)

        self.refresh_callback()
        self.destroy()


# =================================================================
#                   REFLECTIONS
# =================================================================

class ReflectionDialog(tk.Toplevel):
    """
    Simple dialog for adding a new reflection entry.
    """
    def __init__(self, parent, db, refresh_callback):
        super().__init__(parent)
        self.db = db
        self.refresh_callback = refresh_callback
        self.title("Add Reflection")
        self.geometry("400x300")
        ttk.Label(self, text="Reflection Content:").pack(pady=5)
        self.text_area = tk.Text(self, width=50, height=10)
        self.text_area.pack(padx=5, pady=5)
        ttk.Button(self, text="Save", command=self.save_reflection).pack(pady=10)

    def save_reflection(self):
        content = self.text_area.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Validation Error", "Reflection cannot be empty.")
            return
        self.db.add_reflection(content)
        self.refresh_callback()
        self.destroy()


class ReflectionViewer(tk.Toplevel):
    """
    Displays a list of reflections in a scrolling list.
    Allows deletion of specific entries if desired.
    """
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("View Reflections")
        self.geometry("600x400")

        self.tree = ttk.Treeview(self, columns=("Timestamp", "Content"), show='headings')
        self.tree.heading("Timestamp", text="Timestamp")
        self.tree.heading("Content", text="Content")
        self.tree.column("Timestamp", width=150, anchor=tk.CENTER)
        self.tree.column("Content", width=400, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.on_reflection_select)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Delete Reflection", command=self.delete_reflection).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT, padx=5)

        self.populate_reflections()

    def populate_reflections(self):
        self.tree.delete(*self.tree.get_children())
        reflections = self.db.get_reflections()
        for r in reflections:
            self.tree.insert('', tk.END, iid=str(r['id']), values=(r['timestamp'], r['content']))

    def on_reflection_select(self, event):
        pass

    def delete_reflection(self):
        sel = self.tree.selection()
        if not sel:
            return
        reflection_id = int(sel[0])
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete this reflection?")
        if confirm:
            self.db.delete_reflection(reflection_id)
            self.populate_reflections()


# =================================================================
#                   WEEKLY REPORT
# =================================================================

class WeeklyReport(tk.Toplevel):
    """
    Summarizes tasks completed within last 7 days and shows reflection snippets.
    """
    def __init__(self, parent_tasks, reflections):
        super().__init__()
        self.title("Weekly Report")
        self.geometry("800x500")

        # Filter tasks completed in last 7 days
        today = datetime.datetime.now()
        seven_days_ago = today - datetime.timedelta(days=7)

        completed_recently = []
        for t in parent_tasks:
            if t['status'] == 'Completed' and t['completion_timestamp']:
                try:
                    c_dt = datetime.datetime.strptime(t['completion_timestamp'], '%Y-%m-%d %H:%M:%S')
                    if c_dt >= seven_days_ago:
                        completed_recently.append(t)
                except:
                    pass

        # Filter reflections in last 7 days
        recent_reflections = []
        for r in reflections:
            try:
                r_dt = datetime.datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
                if r_dt >= seven_days_ago:
                    recent_reflections.append(r)
            except:
                pass

        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Completed tasks section
        ttk.Label(main_frame, text="Tasks Completed in the Past 7 Days:", font=("Arial", 14, "bold")).pack(anchor=tk.W)
        if not completed_recently:
            ttk.Label(main_frame, text="No tasks completed in this timeframe.").pack(anchor=tk.W, pady=5)
        else:
            for t in completed_recently:
                dt_str = t['completion_timestamp']
                label_txt = f"- {t['title']} (Completed at {dt_str})"
                ttk.Label(main_frame, text=label_txt).pack(anchor=tk.W, pady=2)

        # Reflection section
        ttk.Label(main_frame, text="\nRecent Reflections:", font=("Arial", 14, "bold")).pack(anchor=tk.W)
        if not recent_reflections:
            ttk.Label(main_frame, text="No reflections in this timeframe.").pack(anchor=tk.W, pady=5)
        else:
            box = tk.Text(main_frame, wrap=tk.WORD, height=10)
            box.pack(fill=tk.BOTH, expand=True, pady=5)
            for r in recent_reflections:
                box.insert(tk.END, f"{r['timestamp']}\n{r['content']}\n\n")
            box.configure(state='disabled')


# =================================================================
#                       CALENDAR VIEW
# =================================================================

class CalendarView(tk.Toplevel):
    def __init__(self, parent, tasks):
        super().__init__(parent)
        self.title("Calendar View")
        self.geometry("800x400")
        self.tasks = tasks
        self.view_mode = "month"
        self.create_widgets()

    def create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X)
        ttk.Button(top_frame, text="Month View", command=self.show_month_view).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Week View", command=self.show_week_view).pack(side=tk.LEFT, padx=5)

        self.tree = ttk.Treeview(self, show='headings', height=8)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.show_month_view()

    def show_week_view(self):
        self.view_mode = "week"
        for c in self.tree.get_children():
            self.tree.delete(c)
        self.tree['columns'] = ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
        for col in self.tree['columns']:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        today = datetime.date.today()
        # Start of the week (Monday-based)
        start_day = today - datetime.timedelta(days=today.weekday())
        row = []
        for day in range(7):
            current_date = start_day + datetime.timedelta(days=day)
            date_str = current_date.strftime('%Y-%m-%d')
            tasks_on_date = [t for t in self.tasks if t['date'] == date_str]
            cell_text = f"{current_date.day}\n" + "\n".join([f"{tt['title']} ({tt['priority']})" for tt in tasks_on_date])
            row.append(cell_text)
        self.tree.insert('', tk.END, values=row)

    def show_month_view(self):
        self.view_mode = "month"
        for c in self.tree.get_children():
            self.tree.delete(c)
        self.tree['columns'] = ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
        for col in self.tree['columns']:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)

        today = datetime.date.today()
        first_day = today.replace(day=1)
        start_day = first_day - datetime.timedelta(days=first_day.weekday())

        for week in range(5):
            row = []
            for day in range(7):
                current_date = start_day + datetime.timedelta(days=week*7 + day)
                date_str = current_date.strftime('%Y-%m-%d')
                tasks_on_date = [t for t in self.tasks if t['date'] == date_str]
                cell_text = f"{current_date.day}\n" + "\n".join(
                    [f"{tt['title']} ({tt['priority']})" for tt in tasks_on_date]
                )
                row.append(cell_text)
            self.tree.insert('', tk.END, values=row)


# =================================================================
#                       KANBAN BOARD
# =================================================================

class KanbanBoard(tk.Toplevel):
    def __init__(self, parent, tasks):
        super().__init__(parent)
        self.title("Kanban Board")
        self.geometry("1000x300")
        self.tasks = tasks

        statuses = ["Pending", "Ahead", "Behind", "Completed"]
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        for st in statuses:
            col_frame = ttk.Labelframe(main_frame, text=st)
            col_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
            tasks_in_status = [t for t in tasks if t['status'] == st]
            for t in tasks_in_status:
                lbl = ttk.Label(col_frame, text=f"{t['title']} ({t['date']}) [{t['priority']}]")
                lbl.pack(anchor=tk.W, padx=5, pady=2)


# =================================================================
#                       STATS VIEW
# =================================================================

class StatsView(tk.Toplevel):
    def __init__(self, parent, tasks):
        super().__init__(parent)
        self.title("Statistics")
        self.geometry("600x400")
        self.tasks = tasks
        self.create_chart()

    def create_chart(self):
        status_counts = {}
        for t in self.tasks:
            st = t['status']
            status_counts[st] = status_counts.get(st, 0) + 1

        if plt:
            fig, ax = plt.subplots()
            ax.bar(status_counts.keys(), status_counts.values(), color='skyblue')
            ax.set_title("Tasks by Status")
            ax.set_ylabel("Count")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            canvas = FigureCanvasTkAgg(fig, master=self)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            ttk.Label(self, text="matplotlib is not installed. Cannot display chart.").pack()


# =================================================================
#                    MAIN LAUNCH
# =================================================================

if __name__ == "__main__":
    app = Arcanaeum()
    app.mainloop()
