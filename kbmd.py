import curses
import csv
import os
import json
import time
import textwrap
from datetime import datetime

COLUMNS = ["Backlog", "In Progress", "Blocked / External"]
STATUS_MAP = {
    "To Do": "Backlog",
    "Open": "Backlog",
    "In Progress": "In Progress",
    "Blocked": "Blocked / External",
    "In Review": "Blocked / External",
}

data = {col: [] for col in COLUMNS}
current_col = 0
current_row = 0

# -------------------------
# Persistence
# -------------------------
def get_data_file():
    return os.path.join(os.getcwd(), ".kanban.json")

def save_data():
    with open(get_data_file(), "w") as f:
        json.dump(data, f, indent=2)

def load_data():
    global data
    try:
        with open(get_data_file(), "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        pass

# -------------------------
# CSV Merge (Jira)
# -------------------------

def merge_csv(filepath):
    global data
    existing = {}
    for col, tasks in data.items():
        for task in tasks:
            existing[task["id"]] = (col, task)
    seen_ids = set()
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("Issue key", "")
            if not key:
                continue
            seen_ids.add(key)
            summary = row.get("Summary", "")
            status = row.get("Status", "")
            desc = row.get("Description", "")
            priority = row.get("Priority", "")
            due = row.get("Due date", "")
            if key in existing:
                _, task = existing[key]
                task.update({
                    "title": summary,
                    "description": desc,
                    "priority": priority,
                    "due": due,
                    "jira_status": status
                })
            else:
                column = STATUS_MAP.get(status, "Backlog")
                data[column].append({
                    "id": key,
                    "title": summary,
                    "description": desc,
                    "priority": priority,
                    "due": due,
                    "created": time.time(),
                    "jira_status": status,
                    "source": "jira"
                })
    # Remove stale Jira tasks
    for col in COLUMNS:
        data[col] = [
            t for t in data[col]
            if t.get("source") != "jira" or t["id"] in seen_ids
        ]

# -------------------------
# UI Helpers
# -------------------------
def draw_box(stdscr, y, h, w, x, title=""):
    win = stdscr.subwin(h, w, y, x)
    win.box()
    if title:
        win.addstr(0, 2, f" {title} ")

def wrap_text(text, width):
    return textwrap.wrap(text, width)

def clamp_cursor():
    global current_row
    col = COLUMNS[current_col]
    max_row = max(len(data[col]) - 1, 0)
    current_row = max(0, min(current_row, max_row))

# -------------------------
# Modal
# -------------------------
def open_task_modal(stdscr, task):
    h, w = stdscr.getmaxyx()
    mh, mw = h // 2, w // 2
    y, x = h // 4, w // 4
    win = curses.newwin(mh, mw, y, x)
    fields = ["title", "description", "priority", "due"]
    idx = 0
    scroll = 0
    while True:
        win.clear()
        win.box()
        win.addstr(1, 2, task["id"], curses.A_BOLD)
        for i, field in enumerate(fields):
            val = str(task.get(field, ""))
            marker = ">" if i == idx else " "
            win.addstr(3 + i, 2, f"{marker} {field}: {val[:mw-6]}")
        desc_lines = wrap_text(task.get("description", ""), mw - 6)
        visible = desc_lines[scroll:scroll + (mh - 10)]
        for i, line in enumerate(visible):
            win.addstr(7 + i, 2, line)
        win.addstr(mh - 2, 2, "[Enter] edit [Tab] next [j/k] scroll [q] close")
        key = win.getch()
        if key == 9:
            idx = (idx + 1) % len(fields)
        elif key in [10, 13]:
            field = fields[idx]
            curses.echo()
            win.addstr(3 + idx, 2, f"> {field}: ")
            val = win.getstr().decode("utf-8")
            curses.noecho()
            task[field] = val
        elif key == ord('j'):
            scroll += 1
        elif key == ord('k'):
            scroll = max(0, scroll - 1)
        elif key == ord('q'):
            break

# -------------------------
# Actions
# -------------------------
def add_task_modal(stdscr):
    h, w = stdscr.getmaxyx()
    mh, mw = 10, w // 2
    y, x = h // 2 - mh // 2, w // 4
    win = curses.newwin(mh, mw, y, x)    
    win.box()
    curses.echo()
    fields = ["title", "description", "priority", "due"]
    values = {f: "" for f in fields}
    idx = 0
    while True:
        win.clear()
        win.box()
        win.addstr(1, 2, "New Task", curses.A_BOLD)
        for i, f in enumerate(fields):
            marker = ">" if i == idx else " "
            val = values[f]
            win.addstr(3 + i, 2, f"{marker} {f}: {val[:mw-6]}")
        win.addstr(mh - 2, 2, "[Enter] edit [Tab] next [s] save [q] cancel")
        key = win.getch()
        if key == 9:
            idx = (idx + 1) % len(fields)
        elif key in [10, 13]:
            field = fields[idx]
            win.addstr(3 + idx, 2, f"> {field}: ")
            val = win.getstr().decode("utf-8")
            values[field] = val
        elif key == ord('s'):
            if values["title"]:
                return {
                    "id": f"LOCAL-{int(time.time())}",
                    "title": values["title"],
                    "description": values["description"],
                    "priority": values["priority"],
                    "due": values["due"],
                    "created": time.time(),
                    "jira_status": "",
                    "source": "local"
                }
        elif key == ord('q'):
            return None

def delete_task():
    col = COLUMNS[current_col]
    if data[col]:
        data[col].pop(current_row)

def move_task(direction):
    global current_col, current_row
    col = COLUMNS[current_col]
    if not data[col]:
        return
    task = data[col].pop(current_row)
    new_col = current_col + direction
    if 0 <= new_col < len(COLUMNS):
        data[COLUMNS[new_col]].append(task)
        current_col = new_col
        current_row = len(data[COLUMNS[new_col]]) - 1
    else:
        data[col].insert(current_row, task)

def move_within_column(direction):
    global current_row
    col = COLUMNS[current_col]
    tasks = data[col]
    if len(tasks) <= 1:
        return
    new_row = current_row + direction
    if not (0 <= new_row < len(tasks)):
        return
    tasks[current_row], tasks[new_row] = tasks[new_row], tasks[current_row]
    current_row = new_row

# -------------------------
# Draw
# -------------------------
def draw(stdscr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    col_width = w // len(COLUMNS)
    # HEADER
    repo = os.path.basename(os.getcwd())
    now = datetime.now().strftime("%H:%M")
    draw_box(stdscr, 0, 3, w, 0)
    stdscr.addstr(1, 2, f"KANBAN | {repo} | {now}")
    # BODY
    body_y = 3
    body_h = h - 6
    for i, col in enumerate(COLUMNS):
        x = i * col_width
        draw_box(stdscr, body_y, body_h, col_width, x, col)
        tasks = data[col]
        visible_rows = max(len(tasks), 1)
        for j in range(visible_rows):
            y = body_y + 1 + j
            if j < len(tasks):
                task = tasks[j]
                label = f"{task['id']} [{task.get('priority','')}] {task['title']}"
            else:
                label = "[ + ]"
            if i == current_col and j == current_row:
                attr = curses.A_REVERSE | curses.A_BOLD
            elif i == current_col:
                attr = curses.A_BOLD
            else:
                attr = curses.A_NORMAL
            stdscr.addstr(y, x + 2, label[:col_width - 4], attr)
    # FOOTER
    draw_box(stdscr, h - 3, 3, w, 0)
    stdscr.addstr(
        h - 2, 2,
        "[a] add [d] del [H/L] move [J/K] reorder [Enter] open [r] reload [q] quit"
    )
    stdscr.refresh()

# -------------------------
# Main
# -------------------------
def main(stdscr):
    global current_col, current_row
    curses.curs_set(0)
    load_data()
    while True:
        draw(stdscr)
        key = stdscr.getch()
        col = COLUMNS[current_col]
        # Navigation
        if key in [curses.KEY_LEFT, ord('h')]:
            current_col = max(0, current_col - 1)
            current_row = 0 
        elif key in [curses.KEY_DOWN, ord('j')]:
            if current_row < len(data[col]) - 1:
                current_row += 1
        elif key in [curses.KEY_UP, ord('k')]:
            if current_row > 0:
                current_row -= 1
        elif key in [curses.KEY_RIGHT, ord('l')]:
            current_col = min(len(COLUMNS) - 1, current_col + 1)
            current_row = 0
        # Moving Tasks
        elif key in [curses.KEY_SLEFT, ord('H')]:
            move_task(-1)
            save_data()
        elif key in [curses.KEY_SDOWN, ord('J')]:
            move_within_column(1)
            save_data()
        elif key in [curses.KEY_SUP, ord('K')]:
            move_within_column(-1)
            save_data()
        elif key in [curses.KEY_SRIGHT, ord('L')]:
            move_task(1)
            save_data()
        # Actions
        elif key == ord('a'):
            task = add_task_modal(stdscr)
            if task:
                data[COLUMNS[current_col]].append(task)
                save_data()
        elif key == ord('d'):
            delete_task()
            save_data()
        elif key in [10, 13]:
            if data[col]:
                open_task_modal(stdscr, data[col][current_row])
                save_data()
        elif key == ord('r'):
            curses.echo()
            stdscr.addstr(0, 0, "CSV path: ")
            path = stdscr.getstr().decode("utf-8")
            curses.noecho()
            if path:
                merge_csv(path)
                save_data()
        elif key == ord('q'):
            save_data()
            break
        clamp_cursor()

if __name__ == "__main__":
    curses.wrapper(main)
