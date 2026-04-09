import curses
import curses.textpad
import os
import json
import time
from datetime import datetime
from dateutil.parser import parse

COLUMNS = ["Backlog", "In Progress", "Blocked / External"]
HIDDEN_COLUMN = "Done"

data = {
    "columns": {col: [] for col in COLUMNS + [HIDDEN_COLUMN]},
    "next_id": 1
}

history = []
current_col = 0
current_index = 0  # index into flattened list

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
    except:
        pass

def get_next_id():
    nid = data.get("next_id", 1)
    data["next_id"] = nid + 1
    return f"{nid:05d}"

def snapshot():
    history.append(json.dumps(data))

def undo():
    global data
    if history:
        data = json.loads(history.pop())

# -------------------------
# Tree Helpers
# -------------------------

def flatten_tasks(tasks, parent=None, depth=0, prefix=""):
    flat = []
    for i, t in enumerate(tasks):
        is_last = (i == len(tasks) - 1)
        connector = "└" if is_last else "├"
        line_prefix = prefix + connector if depth > 0 else ""
        flat.append({
            "task": t,
            "parent": parent,
            "index": i,
            "depth": depth,
            "prefix": line_prefix
        })
        extension = " " if is_last else "│"
        if not t.get("collapsed"):
            flat.extend(flatten_tasks(t.get("children", []), t, depth + 1, prefix + extension))
    return flat

# -------------------------
# UI Helpers
# -------------------------

def draw_box(stdscr, y, h, w, x, title="", color=1):
    try:
        attr = curses.color_pair(color)
        stdscr.addstr(y, x, "┌" + "─" * (w - 2) + "┐", attr)
        for i in range(1, h - 1):
            stdscr.addstr(y + i, x, "│" + " " * (w - 2) + "│", attr)
        stdscr.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘", attr)
        if title:
            stdscr.addstr(y, x + 2, f" {title} ", attr | curses.A_BOLD)
    except curses.error:
        pass

# -------------------------
# Modal
# -------------------------

def form_modal(stdscr, title, fields, values, task=None):
    h, w = stdscr.getmaxyx()
    mh, mw = len(fields) * 2 + 8, w // 2
    y, x = h // 2 - mh // 2, w // 4

    curses.curs_set(1)
    idx = 0

    # ✅ Compute fixed label width (aligned inputs)
    max_label_width = max(len(field) for field in fields) + 3  # "> " + ":"

    while True:
        idx = max(0, min(idx, len(fields) - 1))
        f = fields[idx]

        stdscr.erase()
        draw(stdscr)
        draw_box(stdscr, y, mh, mw, x, title)

        for i, field in enumerate(fields):
            ly = y + 2 + i * 2
            lx = x + 2

            prefix = ">" if i == idx else " "
            label = f"{prefix} {field}:"

            stdscr.addstr(ly, lx, label)

            # ✅ aligned textbox start
            box_x = lx + max_label_width + 1
            box_w = mw - (box_x - x) - 2

            display = values[field][:box_w - 1]

            if i == idx:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(ly, box_x, display.ljust(box_w - 1))
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(ly, box_x, display.ljust(box_w - 1))

        # CHILDREN DISPLAY
        if task:
            children = task.get("children", [])
            cy = y + len(fields) * 2 + 2

            stdscr.addstr(cy, x + 2, f"Subtasks ({len(children)}):")

            for i, c in enumerate(children[:5]):
                line = f"{c.get('id')} - {c.get('title')}"
                stdscr.addstr(cy + i + 1, x + 4, line[:mw - 6])

        stdscr.addstr(
            y + mh - 2,
            x + 2,
            "[Tab] next  [Shift+Tab] prev  [Enter] save  [Esc] cancel"
        )

        stdscr.refresh()

        # Active field positioning
        ly = y + 2 + idx * 2
        lx = x + 2

        prefix = ">"
        label = f"{prefix} {f}:"

        box_x = lx + max_label_width + 1
        box_w = mw - (box_x - x) - 2

        editwin = curses.newwin(1, box_w, ly, box_x)
        editwin.addstr(0, 0, values[f][:box_w - 1])

        box = curses.textpad.Textbox(editwin)

        def validator(ch):
            if ch == 27:  # Esc
                raise KeyboardInterrupt
            if ch in (10, 13):  # Enter
                raise StopIteration
            if ch == 9 or ch == curses.KEY_DOWN:  # TAB or ↓
                if idx == len(fields) - 1:
                    return None
                raise EOFError
            if ch == 353 or ch == curses.KEY_UP:  # Shift+Tab or ↑
                if idx == 0:
                    return None
                raise ValueError
            return ch

        try:
            text = box.edit(validator).strip()
            values[f] = text
            idx += 1

        except EOFError:
            values[f] = box.gather().strip()
            idx += 1

        except ValueError:
            values[f] = box.gather().strip()
            idx -= 1

        except KeyboardInterrupt:
            curses.curs_set(0)
            return None

        except StopIteration:
            values[f] = box.gather().strip()
            curses.curs_set(0)
            return values

        if idx >= len(fields):
            break

    curses.curs_set(0)
    return values

# -------------------------
# Modals
# -------------------------
def add_task_modal(stdscr):
    fields = ["title", "description", "priority", "due"]
    values = {f: "" for f in fields}
    result = form_modal(stdscr, "New Task", fields, values)
    if result and result["title"]:
        return {
            "id": "LOCAL-" + get_next_id(),
            "title": result["title"],
            "description": result["description"],
            "priority": result["priority"],
            "created": time.strftime("%Y-%m-%d %H:%M", time.localtime()),
            "due": result["due"],
            "completed_at": None,
            "collapsed": False,
            "children": []
        }
    return None

def open_task_modal(stdscr, task):
    fields = ["title", "description", "priority", "due"]
    values = {f: str(task.get(f, "")) for f in fields}
    result = form_modal(stdscr, task["id"], fields, values, task)
    if result:
        task.update(result)

def confirm_modal(stdscr, message):
    h, w = stdscr.getmaxyx()
    mh, mw = 7, len(message) + 10
    y, x = h // 2 - mh // 2, w // 2 - mw // 2
    while True:
        stdscr.erase()
        draw(stdscr)
        draw_box(stdscr, y, mh, mw, x, "Confirm", 3)
        stdscr.addstr(y + 2, x + 2, message)
        stdscr.addstr(y + 4, x + 2, "[y] yes   [n] no")
        stdscr.noutrefresh()
        curses.doupdate()
        key = stdscr.getch()
        if key in [ord('y'), ord('Y')]:
            return True
        elif key in [ord('n'), ord('N'), 27]:  # ESC = cancel
            return False

def input_modal(stdscr, prompt):
    h, w = stdscr.getmaxyx()
    mw = max(40, len(prompt) + 20)
    mh = 5
    y, x = h // 2 - mh // 2, w // 2 - mw // 2

    curses.curs_set(1)
    draw_box(stdscr, y, mh, mw, x, "Search")

    # Prompt position
    prompt_y = y + 2
    prompt_x = x + 2
    stdscr.addstr(prompt_y, prompt_x, f"{prompt}: ")

    # Input field starts AFTER prompt + space
    input_x = prompt_x + len(prompt) + 2
    input_w = mw - (input_x - x) - 2
    win = curses.newwin(1, input_w, prompt_y, input_x)

    stdscr.refresh()
    box = curses.textpad.Textbox(win)

    try:
        text = box.edit().strip()
    except:
        text = ""

    curses.curs_set(0)
    return text 

def show_completed_modal(stdscr):
    tasks = data["columns"].get(HIDDEN_COLUMN, [])
    if not tasks:
        return

    # Flatten tasks (including subtasks)
    def flatten_with_subtasks(tasks):
        flat_list = []
        for t in tasks:
            flat_list.append((t, 0))  # (task, depth)
            children = t.get("children", [])
            for c in children:
                flat_list.append((c, 1))  # subtasks indented
        return flat_list

    flat = flatten_with_subtasks(tasks)

    h, w = stdscr.getmaxyx()
    mh, mw = min(30, h-4), min(80, w-4)
    y, x = h//2 - mh//2, w//2 - mw//2

    offset = 0  # scrolling offset
    while True:
        stdscr.erase()
        draw(stdscr)  # draw background
        draw_box(stdscr, y, mh, mw, x, "Completed Tasks", color=2)

        # Display visible window
        line_idx = 0
        i = offset
        while line_idx < mh-2 and i < len(flat):
            task, depth = flat[i]

            # Header
            header = "  " * depth + f"## {task.get('title','')} ######"
            if line_idx < mh-2:
                stdscr.addstr(y + 1 + line_idx, x + 2, header[:mw-4])
                line_idx += 1

            # Key-values
            for k in ["id","title","description","priority","created","due","completed_at"]:
                if k in task:
                    val = task[k]
                    line = "  " * depth + f"{k} : {val}"
                    if line_idx < mh-2:
                        stdscr.addstr(y + 1 + line_idx, x + 2, line[:mw-4])
                        line_idx += 1
            i += 1
            if line_idx < mh-2:
                line_idx += 1 

        # Footer
        stdscr.addstr(y + mh - 2, x + 2, "[UP/DOWN] scroll  [q] close")
        stdscr.refresh()

        key = stdscr.getch()
        if key in [ord('q'), 27]:  # q or ESC
            break
        elif key in [curses.KEY_DOWN, ord('j')]:
            if offset < len(flat) - 1:
                offset += 1
        elif key in [curses.KEY_UP, ord('k')]:
            if offset > 0:
                offset -= 1

# -------------------------
# Actions
# -------------------------
def complete_task(flat):
    global current_index
    if current_index >= len(flat):
        return
    item = flat[current_index]
    task = item["task"]
    parent = item["parent"]
    # Remove from current location
    if parent is None:
        col = COLUMNS[current_col]
        data["columns"][col].pop(item["index"])
    else:
        parent["children"].pop(item["index"])
    task["completed_at"] = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    data["columns"][HIDDEN_COLUMN].append(task) # Add to hidden column 
    current_index = max(0, current_index - 1)

def delete_task(flat_list):
    global current_index
    if not flat_list:
        return
    item = flat_list[current_index]
    parent = item["parent"]
    idx = item["index"]
    if parent is None:
        col = COLUMNS[current_col]
        data["columns"][col].pop(idx)
    else:
        parent["children"].pop(idx)
    current_index = max(0, current_index - 1)

def move_task(direction, flat):
    global current_col, current_index

    if current_index >= len(flat):
        return

    item = flat[current_index]
    task = item["task"]
    parent = item["parent"]

    # Only allow top-level tasks to move columns
    if parent is not None:
        return

    col = COLUMNS[current_col]
    idx = item["index"]

    # Remove from current column
    task = data["columns"][col].pop(idx)

    new_col = current_col + direction

    if 0 <= new_col < len(COLUMNS):
        # ✅ Move task
        data["columns"][COLUMNS[new_col]].append(task)
        current_col = new_col

        # ✅ Recompute flat list
        new_flat = flatten_tasks(data["columns"][COLUMNS[new_col]])

        # ✅ Find the moved task and set focus to it
        for i, it in enumerate(new_flat):
            if it["task"] is task:
                current_index = i
                break
    else:
        # Put it back if invalid move
        data["columns"][col].insert(idx, task)

def move_within_column(direction, flat):
    global current_index
    if current_index >= len(flat):
        return
    item = flat[current_index]
    parent = item["parent"]
    idx = item["index"]
    # Determine sibling list
    if parent is None:
        siblings = data["columns"][COLUMNS[current_col]]
    else:
        siblings = parent["children"]
    if len(siblings) <= 1:
        return
    new_idx = idx + direction
    if not (0 <= new_idx < len(siblings)):
        return
    task = siblings.pop(idx)
    siblings.insert(new_idx, task)
    new_flat = flatten_tasks(data["columns"][COLUMNS[current_col]])
    for i, it in enumerate(new_flat):
        if it["task"] is task:
            current_index = i
            break

def promote(flat):
    global current_index
    item = flat[current_index]
    parent = item["parent"]
    if parent is None:
        return
    grandparent = None
    for f in flat:
        if f["task"] is parent:
            grandparent = f["parent"]
            break
    parent["children"].pop(item["index"])
    if grandparent is None:
        data["columns"][COLUMNS[current_col]].append(item["task"])
    else:
        grandparent["children"].append(item["task"])


def demote(flat):
    global current_index
    if current_index == 0:
        return
    item = flat[current_index]
    prev = flat[current_index - 1]
    siblings = data["columns"][COLUMNS[current_col]] if item["parent"] is None else item["parent"]["children"]
    siblings.pop(item["index"])
    prev["task"].setdefault("children", []).append(item["task"])

# -------------------------
# Draw
# -------------------------
def draw(stdscr):
    h, w = stdscr.getmaxyx()
    stdscr.erase()

    col_width = w // len(COLUMNS)

    draw_box(stdscr, 0, 3, w, 0)
    repo = os.path.basename(os.getcwd())
    now = datetime.now().strftime("%H:%M")

    stdscr.addstr(1, 2, "KBMD")
    stdscr.addstr(1, (w // 2) - (len(repo) // 2), repo)
    stdscr.addstr(1, w - len(now) - 4, now)

    body_y = 3
    body_h = h - 6

    for i, col in enumerate(COLUMNS):
        x = i * col_width

        color = 4 if col == "Backlog" else 2 if col == "In Progress" else 3

        draw_box(stdscr, body_y, body_h, col_width, x, col, color)

        flat = flatten_tasks(data["columns"][col])

        for j in range(len(flat) + 1):
            y = body_y + 1 + j
            if j < len(flat):
                item = flat[j]
                task = item["task"]
                depth = item["depth"]
                prefix = item.get("prefix", "")
                collapsed = task.get("collapsed", False)
                marker = "+" if collapsed else "-"
                label = f"{prefix}{marker} [{task.get('priority','')}] {task['title']}"            
                priority = task.get("priority", "").lower()
                if priority == "high":
                    color = curses.color_pair(3)
                elif priority == "medium":
                    color = curses.color_pair(5)
                elif priority == "low":
                    color = curses.color_pair(2)
                else:
                    color = curses.color_pair(1)
            else:
                label = "[ + ]"
            
            # Preserve selection highlight
            if i == current_col and j == current_index:
                attr = color | curses.A_REVERSE | curses.A_BOLD
            elif i == current_col:
                attr = color | curses.A_BOLD
            else:
                attr = color
            try:
                if label == "[ + ]": # if this isn't a task, then 
                    centered_x = x + (col_width - len(label)) // 2 # find the center of the column
                    stdscr.addstr(y, centered_x, label, attr) # write the [ + ] button to the center 
                else: # otherwise
                    stdscr.addstr(y, x + 2, label[:col_width - 4], attr) # write the task to the buffer 
            except: # if that doesn't work,
                pass # do nothing, rather than break the application

    draw_box(stdscr, h - 3, 3, w, 0)
    stdscr.addstr(h - 2, 2, "[a] add [s] sub [c] complete [d] delete [H/L] status [J/K] priority [tab] demote [TAB] promote [Enter] select [q] quit") # write the footer text
    stdscr.noutrefresh()

# -------------------------
# Main
# -------------------------

def main(stdscr):
    # INIT 
    global current_col, current_index
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_CYAN, -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)
    load_data()
    # SCREEN BUFFER
    needs_redraw = True 
    while True:
        if needs_redraw:
            draw(stdscr)
            curses.doupdate()
            needs_redraw = False 
    # INPUT 
        key = stdscr.getch()
        if key == -1:
            time.sleep(0.01) # Ensures 60 Hz refresh rate screen buffer, prevents flicker
            continue 
        col = COLUMNS[current_col]
        flat = flatten_tasks(data["columns"][col])
        # Move Focus Left
        if key in [curses.KEY_LEFT, ord('h')]:
            current_col = max(0, current_col - 1)
            current_index = 0
        # Move Focus Down 
        elif key in [curses.KEY_DOWN, ord('j')]:
            current_index = min(len(flat), current_index + 1)
        # Move Focus Up 
        elif key in [curses.KEY_UP, ord('k')]:
            current_index = max(0, current_index - 1)
        # Move Focus Right
        elif key in [curses.KEY_RIGHT, ord('l')]:
            current_col = min(len(COLUMNS) - 1, current_col + 1)
            current_index = 0 
        # Move Task Left 
        elif key == ord('H'):
            snapshot()
            move_task(-1, flat)
            save_data()
        # Move Task Right  
        elif key == ord('L'):
            snapshot()
            move_task(1, flat)
            save_data()
        # Move Task Down 
        elif key == ord('J'):
            snapshot()
            move_within_column(1, flat)
            save_data()
        # Move Task Up 
        elif key == ord('K'):
            snapshot()
            move_within_column(-1, flat)
            save_data()
        # Add Task 
        elif key == ord('a'):
            snapshot() 
            task = add_task_modal(stdscr)
            if task:
                data["columns"][col].append(task)
                save_data()
        # Add Subtask 
        elif key == ord('s'):
            snapshot()
            if current_index < len(flat):
                parent = flat[current_index]["task"]
                sub = add_task_modal(stdscr)
                if sub:
                    parent.setdefault("children", []).append(sub)
                    save_data()
        # Complete Task 
        elif key == ord('c'):
            snapshot()
            if current_index >= len(flat):
                continue  # you're on [ + ], nothing to delete
            item = flat[current_index]
            task = item["task"]
            children = task.get("children", [])
            msg = f"Complete '{task['title']}'"
            if children:
                msg += f" and {len(children)} subtask(s)?"
            else:
                msg += "?"
            if confirm_modal(stdscr, msg):
                complete_task(flat)
                save_data()
        # Show Completed Tasks Modal / Trophy Screen
        elif key == ord('C'):  # capital C
            show_completed_modal(stdscr)
        # Delete Task 
        elif key == ord('d'):
            snapshot()
            if current_index >= len(flat):
                continue  # you're on [ + ], nothing to delete
            item = flat[current_index]
            task = item["task"]
            children = task.get("children", [])
            msg = f"Delete '{task['title']}'"
            if children:
                msg += f" and {len(children)} subtask(s)?"
            else:
                msg += "?"
            if confirm_modal(stdscr, msg):
                delete_task(flat)
                save_data()
        # Press Enter - multi-use/contextual
        elif key in [10, 13]:  # Enter
            snapshot()
            if current_index >= len(flat): # If we're on the [ + ] row, then
                task = add_task_modal(stdscr) # we should add a new task 
                if task: # if the new task exists, then 
                    data["columns"][col].append(task) # add it to the datatstream
                    save_data() # save state after every change 
            else:
                item = flat[current_index] # Editing an existing task or subtask
                open_task_modal(stdscr, item["task"]) # open the task we're selecting
                save_data() # save state after every change
        # Demote Tasks
        elif key == 9:  # TAB
            snapshot()
            demote(flat)
        #Promote Tasks 
        elif key == 353:  # SHIFT+TAB
            snapshot()
            promote(flat)
        elif key == ord('z'):
            undo()
        elif key == ord(' '):
            if current_index < len(flat):
                task = flat[current_index]["task"]
                task["collapsed"] = not task.get("collapsed", False)

        elif key == ord('/'):
            query = input_modal(stdscr, "Search")
            if query:
                found = False
                for ci, col_name in enumerate(COLUMNS):
                    flat_col = flatten_tasks(data["columns"][col_name])
                    for i, item in enumerate(flat_col):
                        if query.lower() in item["task"]["title"].lower():
                            current_col = ci
                            current_index = i
                            found = True
                            break
                    if found:
                        break 
        # Quit The Application
        elif key == ord('q'):
            save_data()
            break 

        needs_redraw = True
        current_index = min(current_index, len(flatten_tasks(data["columns"][COLUMNS[current_col]])))

if __name__ == "__main__":
    curses.wrapper(main)
