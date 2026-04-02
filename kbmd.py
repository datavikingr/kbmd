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
filter_text = ""

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
            summary = row.get("Summary", "")
            status = row.get("Status", "")
            desc = row.get("Description", "")
            priority = row.get("Priority", "")
            due = row.get("Due date", "")

            if not key:
                continue

            seen_ids.add(key)

            if key in existing:
                col, task = existing[key]
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
            if t["source"] != "jira" or t["id"] in seen_ids
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

def filter_tasks(tasks):
    if not filter_text:
        return tasks
    q = filter_text.lower()
    return [t for t in tasks if q in t["title"].lower() or q in t.get("description","").lower()]

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

        # Fields
        for i, field in enumerate(fields):
            val = str(task.get(field, ""))
            marker = ">" if i == idx else " "
            win.addstr(3 + i, 2, f"{marker} {field}: {val[:mw-6]}")

        # Description view
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

def add_task(stdscr):
    curses.echo()
    stdscr.addstr(0, 0, "New task: ")
    text = stdscr.getstr().decode("utf-8")
    curses.noecho()

    if text:
        data[COLUMNS[current_col]].append({
            "id": f"LOCAL-{int(time.time())}",
            "title": text,
            "description": "",
            "priority": "",
            "due": "",
            "created": time.time(),
            "jira_status": "",
            "source": "local"
        })

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

# -------------------------
# Draw
# -------------------------

def draw(stdscr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    col_width = w // 3

    repo = os.path.basename(os.getcwd())
    now = datetime.now().strftime("%H:%M")

    stdscr.addstr(0, 0, f" KANBAN | {repo} | {now}".ljust(w))

    for i, col in enumerate(COLUMNS):
        x = i * col_width
        draw_box(stdscr, 1, h - 5, col_width, x, col)

        tasks = filter_tasks(data[col])

        for j, task in enumerate(tasks):
            label = f"{task['id']} [{task.get('priority','')}] {task['title']}"

            if i == current_col and j == current_row:
                attr = curses.A_REVERSE | curses.A_BOLD
            elif i == current_col:
                attr = curses.A_BOLD
            else:
                attr = curses.A_NORMAL

            stdscr.addstr(2 + j, x + 2, label[:col_width - 4], attr)

    stdscr.addstr(h - 2, 0,
        "[a] add [d] del [H/L] move [Enter] open [/] search [r] reload [q] quit"
    )

    stdscr.refresh()

# -------------------------
# Main
# -------------------------

def main(stdscr):
    global current_col, current_row, filter_text

    curses.curs_set(0)
    load_data()

    while True:
        draw(stdscr)
        key = stdscr.getch()
        col = COLUMNS[current_col]

        if key in [curses.KEY_RIGHT, ord('l')]:
            current_col = min(2, current_col + 1)
            current_row = 0

        elif key in [curses.KEY_LEFT, ord('h')]:
            current_col = max(0, current_col - 1)
            current_row = 0

        elif key in [curses.KEY_DOWN, ord('j')]:
            if data[col]:
                current_row = min(len(data[col]) - 1, current_row + 1)

        elif key in [curses.KEY_UP, ord('k')]:
            current_row = max(0, current_row - 1)

        elif key == ord('H'):
            move_task(-1)
            save_data()

        elif key == ord('L'):
            move_task(1)
            save_data()

        elif key == ord('a'):
            add_task(stdscr)
            save_data()

        elif key == ord('d'):
            delete_task()
            save_data()

        elif key in [10, 13]:
            if data[col]:
                open_task_modal(stdscr, data[col][current_row])
                save_data()

        elif key == ord('/'):
            curses.echo()
            stdscr.addstr(0, 0, "/")
            filter_text = stdscr.getstr().decode("utf-8")
            curses.noecho()
            current_row = 0

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

if __name__ == "__main__":
    curses.wrapper(main)
