import curses
import csv
import os
import json
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

# ---------- UI HELPERS ----------

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_WHITE)

def draw_box(stdscr, y, h, w, x=0, label=""):
    stdscr.addstr(y, x, "┌" + "─" * (w - 2) + "┐")
    for i in range(1, h - 1):
        stdscr.addstr(y + i, x, "│" + " " * (w - 2) + "│")
    stdscr.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘")
    if label:
        stdscr.addstr(y, x + 2, f" {label} ")

def small_prompt(stdscr, prompt_str):
    curses.echo()
    stdscr.addstr(curses.LINES - 1, 0, prompt_str)
    stdscr.clrtoeol()
    stdscr.refresh()
    val = stdscr.getstr().decode()
    curses.noecho()
    return val

# ---------- CORE UI ----------
def draw_kanban(stdscr):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    col_width = w // 3

    # Header
    now = datetime.now().strftime("%H:%M")
    repo = os.path.basename(os.getcwd())
    stdscr.addstr(0, 0, f" KANBAN | {repo} | {now}".ljust(w), curses.color_pair(1))
    for i, col in enumerate(COLUMNS):
        x = i * col_width
        draw_box(stdscr, 1, h - 4, col_width, x, col)
        tasks = data[col]
        for j, task in enumerate(tasks):
            label = f"{task['id']} {task['title']}"
            attr = curses.A_REVERSE if (i == current_col and j == current_row) else curses.A_NORMAL
            stdscr.addstr(2 + j, x + 1, label[:col_width - 2], attr)
    
    # Footer
    stdscr.addstr(
        h - 1, 0,
        "[a] add  [d] del  [H/L] move  [hjkl] nav  [r] load CSV  [q] quit",
        curses.color_pair(3)
    )
    stdscr.refresh()

# ---------- DATA ----------
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

def load_csv(filepath):
    global data
    new_data = {col: [] for col in COLUMNS}
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("Status", "")
            key = row.get("Issue key", "")
            summary = row.get("Summary", "")
            column = STATUS_MAP.get(status, "Backlog")
            new_data[column].append({
                "id": key,
                "title": summary
            })
    data = new_data

def add_task(stdscr):
    global data
    text = small_prompt(stdscr, "New task: ")
    if text:
        data[COLUMNS[current_col]].append({
            "id": "LOCAL",
            "title": text
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

# ---------- MAIN LOOP ----------

def main(stdscr):
    global current_col, current_row
    curses.curs_set(0)
    init_colors()
    load_data()
    while True:
        draw_kanban(stdscr)
        key = stdscr.getch()
        col = COLUMNS[current_col]
        if key in [curses.KEY_RIGHT, ord('l')]:
            current_col = min(len(COLUMNS) - 1, current_col + 1)
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
        elif key == ord("a"):
            add_task(stdscr)
            save_data()
        elif key == ord("d"):
            delete_task()
            save_data()
            current_row = max(0, current_row - 1)
        elif key == ord("r"):
            path = small_prompt(stdscr, "CSV path: ")
            if path:
                load_csv(path)
                current_row = 0
                current_col = 0
            save_data()
        elif key == ord("q"):
            save_data()
            break

if __name__ == "__main__":
    curses.wrapper(main)
