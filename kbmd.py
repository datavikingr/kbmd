import curses
import curses.textpad 
import os
import json
import time
from datetime import datetime

COLUMNS = ["Backlog", "In Progress", "Blocked / External"]

data = {
    "columns": {col: [] for col in COLUMNS},
    "next_id": 1
}
current_col = 0
current_row = 0

# -------------------------
# Persistence
# -------------------------
def get_data_file(): # find the save file helper 
    # different projects have different todo lists.
    # therefore, local file. feel free to track in vc or add to gitignore
    return os.path.join(os.getcwd(), ".kanban.json") # grab the local file 

def save_data(): # writes data to local file 
    with open(get_data_file(), "w") as f: # get local file, open it 
        json.dump(data, f, indent=2) # write the data 

def load_data(): # sets app state to that of local file 
    global data # set global variable
    # if the file doesn't exist, that just means this is new directory and we should start with a new file
    try: # find file path ...
        with open(get_data_file(), "r") as f: # get local file if it exists
            data = json.load(f) # set the global datastream to match file state 
    except: # ... graceful "or not" path 
        pass # then nothing, init as from scratch

def get_next_id():
    nid = data.get("next_id", 1) # get the json's next_id variable 
    data["next_id"] = nid + 1 # iterate the global next_id in the datastream 
    return f"{nid:05d}" # return the integer with 5 places

# -------------------------
# UI Helpers
# -------------------------
def draw_box(stdscr, y, h, w, x, title="", color=1): # build modal
    try: # try to draw to screen buffer 
        attr = curses.color_pair(color) # get color
        stdscr.addstr(y, x, "┌" + "─" * (w - 2) + "┐", attr)  # top line of box 
        for i in range(1, h - 1): # walls to desired height, minus the floor
            stdscr.addstr(y + i, x, "│" + " " * (w - 2) + "│", attr) # each wall 
        stdscr.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘", attr) # floor
        if title: # if the modal was passed a title, then 
            stdscr.addstr(y, x + 2, f" {title} ", attr | curses.A_BOLD) # write the title to the box, boldly.
    except curses.error: # if we can't draw that for some reason,
        pass # simply don't, rather than break the application

def clamp_cursor(): # Keep the cusor in bounds 
    global current_row # forcefully set y 
    col = COLUMNS[current_col] # determine x
    max_row = max(len(data["columns"][col]), 1) # max y is the vertical length of the given column above, minus 1 for 0-indexing
    current_row = max(0, min(current_row, max_row)) # apply constraint current row to the bounds of the arena

# -------------------------
# Modal Input Engine
# -------------------------
def form_modal(stdscr, title, fields, values):
    h, w = stdscr.getmaxyx()
    mh, mw = len(fields) * 2 + 6, w // 2
    y, x = h // 2 - mh // 2, w // 4
    curses.curs_set(1)
    idx = 0  # start at first field 
    while True:
        # constrain idx to valid field range
        idx = max(0, min(idx, len(fields) - 1))
        f = fields[idx]
        stdscr.erase()
        draw(stdscr)
        draw_box(stdscr, y, mh, mw, x, title)
        # Draw all fields (show values from previous edits)
        for i, field in enumerate(fields):
            label_y = y + 2 + i * 2
            label_x = x + 2
            stdscr.addstr(label_y, label_x, f"{field}:")
            box_x = label_x + len(field) + 2
            box_w = mw - len(field) - 6
            display_text = values[field][:box_w-1]
            stdscr.addstr(label_y, box_x, display_text.ljust(box_w - 1))
            if i == idx:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(label_y, label_x, f"{field}:")
                stdscr.attroff(curses.A_REVERSE)
        stdscr.addstr(y + mh - 2, x + 2, "[Tab] next  [Shift+Tab] prev  [Enter] save  [Esc] cancel")
        stdscr.refresh()
        # Input window for active field
        label_y = y + 2 + idx * 2
        box_x = x + len(f) + 4
        box_w = mw - len(f) - 8
        editwin = curses.newwin(1, box_w, label_y, box_x)
        editwin.addstr(0, 0, values[f])
        box = curses.textpad.Textbox(editwin)
        def validator(ch):
            if ch in (27,):  # ESC → cancel
                raise KeyboardInterrupt
            if ch == 9:  # Tab → next field
                raise EOFError
            if ch == 353:  # Shift+Tab → prev field
                raise ValueError
            if ch in (10, 13):  # Enter → end editing
                return 7  # Ctrl+G ends editing for this field
            return ch 
        try:
            text = box.edit(validator).strip()
            values[f] = text
            idx += 1  # next field
        except EOFError:  # Tab pressed
            values[f] = box.gather().strip()
            idx += 1
        except ValueError:  # Shift+Tab pressed
            values[f] = box.gather().strip()
            idx -= 1
        except KeyboardInterrupt:  # ESC pressed → cancel modal
            curses.curs_set(0)
            return None 
        if idx >= len(fields):
            break  # all fields completed
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
            "id": get_next_id(),
            "title": result["title"],
            "description": result["description"],
            "priority": result["priority"],
            "due": result["due"],
            "created": time.time(),
        }
    return None

def open_task_modal(stdscr, task):
    fields = ["title", "description", "priority", "due"]
    values = {f: str(task.get(f, "")) for f in fields}
    result = form_modal(stdscr, task["id"], fields, values)
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

# -------------------------
# Actions
# -------------------------
def delete_task():
    col = COLUMNS[current_col]
    if current_row < len(data["columns"][col]):
        data["columns"][col].pop(current_row)

def move_task(direction):
    global current_col, current_row
    col = COLUMNS[current_col]
    if current_row >= len(data["columns"][col]):
        return 
    task = data["columns"][col].pop(current_row)
    new_col = current_col + direction 
    if 0 <= new_col < len(COLUMNS):
        data["columns"][COLUMNS[new_col]].append(task)
        current_col = new_col
        current_row = len(data["columns"][COLUMNS[new_col]]) - 1
    else:
        data["columns"][col].insert(current_row, task)

def move_within_column(direction):
    global current_row
    col = COLUMNS[current_col]
    tasks = data["columns"][col]
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
    # Screen Construction
    h, w = stdscr.getmaxyx() # get the lay of the canvas
    stdscr.erase() # wipe the canvas clean
    col_width = w // len(COLUMNS) # 3 columns. Divide total width by 3, sans remainder, get column width.
    # Header box
    draw_box(stdscr, 0, 3, (col_width * 3), 0) # draw title box  
    repo = os.path.basename(os.getcwd()) # find the name of the 'repo' by getting cwd 
    now = datetime.now().strftime("%H:%M")# time check, because I code at night 
    stdscr.addstr(1, 2, "KBMD") # write title in top left inside of box 
    stdscr.addstr(1, (w // 2) - (len(repo) // 2), repo) # write cwd in center, inside box 
    stdscr.addstr(1, w - len(now) - 4, now) # write time in top right, inside box 
    # Body of application 
    body_y = 3 # starting vertical index for body (remember: index at 0)
    body_h = h - 6 # vertical height of body, leaving space for header and footer
    for i, col in enumerate(COLUMNS):
        x = i * col_width
        # ["Backlog":"CYAN":4,"In Progress":"GREEN":2,"Blocked / External":"RED":3]
        if col == "Backlog":
            color = 4
        elif col == "In Progress":
            color = 2
        elif col == "Blocked / External":
            color = 3
        else:
            color = 1
        draw_box(stdscr, body_y, body_h, col_width, x, col, color)
        tasks = data["columns"][col] # find this column in the global data stream
        rows = len(tasks) # count tasks in this column
        for j in range(rows + 1): # iterate over the rows set above 
            y = body_y + 1 + j # determine location, body "zero" plus border plus task #
            if j < rows: # if current iteration is less than the number of tasks set above  
                task = tasks[j] # assign this task's data to this object 
                label = f"[{task.get('priority','')}] {task['title']}" # and build our "task object" from the UI perspective
            else: # if the current iteration = actual task length set above, then
                label = "[ + ]" # we draw the add-task button
            if i == current_col and j == current_row: # if list item is currently selected, then 
                attr = curses.A_REVERSE | curses.A_BOLD # boldly reverse colors 
            elif i == current_col: # If cursor is in this column, then 
                attr = curses.A_BOLD # be bold 
            else: # otherwise, 
                attr = curses.A_NORMAL # just be normal
            try: # try to 
                if j < rows: # if this is a task, then 
                    stdscr.addstr(y, x + 2, label[:col_width - 4], attr) # write the task to the buffer 
                else: # otherwise, 
                    centered_x = x + (col_width - len(label)) // 2 # find the center of the column
                    stdscr.addstr(y, centered_x, label, attr) # write the [ + ] button to the center 
            except: # if that doesn't work,
                pass # do nothing, rather than break the application
    # Footer box 
    draw_box(stdscr, h - 3, 3, w, 0) # draw the footer box 
    stdscr.addstr(h - 2, 2, "[a] add [d] del [H/L] move [J/K] reorder [Enter] open [q] quit") # write the footer text
    stdscr.noutrefresh() # build the changes for the frame buffer to execute after timer completes, .1 s from now.

# -------------------------
# Main
# -------------------------
def main(stdscr):
# INIT    
    global current_col, current_row # establish global variables: cursor focus y & x, respectively
    curses.curs_set(0) 
    stdscr.nodelay(True) # When I say, draw, you draw 
    curses.start_color() # init color
    curses.use_default_colors() # establish the foundation
    curses.init_pair(1, curses.COLOR_WHITE, -1) # set default
    curses.init_pair(2, curses.COLOR_GREEN, -1) # set in progress
    curses.init_pair(3, curses.COLOR_RED, -1) # set blocked/external
    curses.init_pair(4, curses.COLOR_CYAN, -1)  # backlog
    load_data() # what it says on the can
    needs_redraw = True # write what just loaded to screen
# MAIN LOOP    
    while True: # loop
        # screen buffer
        if needs_redraw: # if reality and expected screens are different, then
            draw(stdscr) # draw the buffer to match expected
            curses.doupdate() # update the screen itself to match the buffer
            needs_redraw = False # reset state to zero
        key = stdscr.getch() # check for input
        if key == -1: # if nothing is entered, then
            time.sleep(0.01) # wait - this is the actual mechanism of the buffer, the 'delay' portion
            continue # repeat parent while-loop from the top
        col = COLUMNS[current_col] # where am I
        # Move Cursor Left 
        if key in [curses.KEY_LEFT, ord('h')]: # input left
            current_col = max(0, current_col - 1) # go left, clamped so the focus/cursor doesn't wander off into the night
            current_row = 0 # start focus/cursor at the top, index 0
       # Move Cursor Right 
        elif key in [curses.KEY_RIGHT, ord('l')]: # input right
            current_col = min(len(COLUMNS) - 1, current_col + 1) # go right, clamped so the focus/cursor doesn't wander off
            current_row = 0 # start from the top, index 0
        # Move Cursor Down 
        elif key in [curses.KEY_DOWN, ord('j')]: # input down
            current_row += 1 # iterate cursor down a position
        # Move Cursor Up 
        elif key in [curses.KEY_UP, ord('k')]: # input up
            current_row -= 1 # iterate cursor position up by one
        # Move Task Left 
        elif key == ord('H'): # input Shift H 
            move_task(-1) # move the task left one column
            save_data() # save after every change of state
        # Move Task Right  
        elif key == ord('L'): # Input Shift L 
            move_task(1) # move the task right one column 
            save_data() # save after every change of state 
        # Move Task Down 
        elif key == ord('J'): # Input Shift J 
            move_within_column(1) # move the task down one position in the column 
            save_data() # save after every change of state 
        # Move Task Up 
        elif key == ord('K'): # Input Shift K 
            move_within_column(-1) # move thetask up one position in the column 
            save_data() # save state after every change
        # Add task 
        elif key == ord('a'): # input a 
            task = add_task_modal(stdscr) # build a new task and catch it as an object
            if task: # if the object has stuff in it, then 
                data["columns"][COLUMNS[current_col]].append(task) # build the task in the current column 
                save_data() # save state after every change 
        # Delete Task
        elif key == ord('d'): # input d
            col = COLUMNS[current_col] # determine location 
            if current_row < len(data["columns"][col]): # If we're not on the [ + ] button
                task = data["columns"][col][current_row] # get the task 
                if confirm_modal(stdscr, f"Delete '{task['title']}'?"): # confirmation box yes, then 
                    delete_task() # do the thing
                    save_data() # save state after every change 
        # Press Enter - multi-use/contextual
        elif key in [10, 13]: # input enter 
            if current_row >= len(data["columns"][col]): # if we're hovering over [ + ], then 
                task = add_task_modal(stdscr) # add new task and catch it as an object 
                if task: # if that object has stuff in it, then 
                    data["columns"][col].append(task) # add it to the current column 
                    save_data() # save state after every change 
            else: # it's not a new task, so 
                open_task_modal(stdscr, data["columns"][col][current_row]) # we're going to edit the task we're selecting
                save_data() # save state after every change 
        # Quit the Program
        elif key == ord('q'): # input q 
            save_data() # final save 
            break # leave the loop, terminating the program 
        clamp_cursor() # ensure the cursor can't exceed bounds. 
        needs_redraw = True # set state to need to redraw, for having collected changes above

if __name__ == "__main__": # This must be called directly and not as a library
    curses.wrapper(main) # begin init & main loop 
