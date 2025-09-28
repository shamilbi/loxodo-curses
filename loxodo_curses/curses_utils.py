import curses
from collections.abc import Callable


def win_addstr(
    win: curses.window, row: int, col: int, s: str, attr: int = 0, border: int = 0, align: int = -1
):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    'align: -1 (left), 0(center), 1(right)'
    try:
        _, cols = win.getmaxyx()
        cols2 = cols - col - border
        s = s[:cols2]
        if align == 0:
            s = f'{s:^{cols2}}'
        elif align > 0:
            s = f'{s:>{cols2}}'
        win.addstr(row, col, s, attr)
    except curses.error:
        # https://docs.python.org/3/library/curses.html#curses.window.addstr
        # Attempting to write to the lower right corner of a window, subwindow, or pad
        # will cause an exception to be raised after the string is printed.
        pass


def win_center(screen: curses.window, rows: int, cols: int, header: str, color: int = 0) -> curses.window:
    max_rows, max_cols = screen.getmaxyx()
    rows = min(rows, max_rows)
    cols = min(cols, max_cols)
    y = (max_rows - rows) // 2
    x = (max_cols - cols) // 2

    win = screen.derwin(rows, cols, y, x)
    win.keypad(True)
    win.erase()
    if color:
        win.attrset(color)
    win.box()

    header = header[:cols]
    x = (cols - len(header)) // 2
    win_addstr(win, 0, x, header)

    return win


def ask_delete(screen: curses.window, color: int = 0) -> bool:
    header = 'Delete current record'
    win = win_center(screen, 5, 30, header, color=color)

    win_addstr(win, 1, 1, 'Are you sure?', border=1, align=0)
    win_addstr(win, 3, 1, 'Press Y to delete ...', border=1, align=0)

    try:
        ch = win.getch()
        if ch == ord('Y'):
            return True
        return False
    except curses.error:
        return False
    finally:
        # https://stackoverflow.com/questions/2575409/how-do-i-delete-a-curse-window-in-python-and-restore-background-window
        win.erase()
        del win
        screen.touchwin()


def win_help(screen, help_: list[tuple[str, str]]):  # pylint: disable=too-many-locals
    '''
    help_ = [
        (key1, help1),
        (key2, help2),
        ...
    ]
    '''
    header = "Help information:"
    footer = "Press any key to continue..."

    lmax = max(len(i[0]) for i in help_)  # (lmax) - help

    def iter_help():
        for i, j in help_:
            yield f'{i:<{lmax}} - {j}'  # keys - help

    rows = len(help_) + 1  # footer=1
    rows2 = rows + 2  # border=2
    cols = max(len(header), max(len(i) for i in iter_help()), len(footer))
    cols2 = cols + 2  # border=2

    win = win_center(screen, rows2, cols2, header)
    rows2, cols2 = win.getmaxyx()

    row = 0
    col = 1
    for s in iter_help():
        row += 1
        win_addstr(win, row, col, s, border=1)
    row += 1
    win_addstr(win, row, col, footer, border=1)

    # Wait for any key press
    win.getch()

    # https://stackoverflow.com/questions/2575409/how-do-i-delete-a-curse-window-in-python-and-restore-background-window
    win.erase()
    del win
    screen.touchwin()


class List:
    '''
    A projection of an array of records r0...rX to a window lines of string s0...sY
    where si = get_rec(j) = rj -> str, s(i+1) = get_rec(j+1), j < len_recs()
    and changing cursor (i) leads to call refresh_deps()
    '''

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        win: curses.window,
        get_rec: Callable[[int], str],
        len_recs: Callable[[], int],
        refresh_deps: Callable[[], None],
        current_color: int = curses.A_BOLD,
    ):
        self.win = win
        self.get_rec = get_rec
        self.len_recs = len_recs
        self.refresh_deps = refresh_deps
        self.current_color = current_color

        self.win.keypad(True)

        self.cur = 0  # cursor y
        self.idx = 0  # source index

    def refresh(self):
        self.win.erase()
        len_ = self.len_recs()
        if len_:
            rows, _ = self.win.getmaxyx()
            if not self.idx < len_:  # deleted
                self.idx = len_ - 1
            self.cur = min(self.cur, self.idx)
            for i in range(rows):
                idx = self.idx - self.cur + i
                if not idx < len_:
                    break
                s = self.get_rec(idx)
                if i == self.cur:
                    win_addstr(self.win, i, 0, s, attr=self.current_color)
                else:
                    win_addstr(self.win, i, 0, s)
            self.win.move(self.cur, 0)
        self.win.refresh()
        self.refresh_deps()

    def scroll_top(self):
        self.idx = self.cur = 0
        self.refresh()

    def scroll_bottom(self):
        len_ = self.len_recs()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        self.cur = min(rows - 1, len_ - 1)
        self.idx = len_ - 1
        self.refresh()

    def scroll_down(self):
        len_ = self.len_recs()
        if not len_ or not self.idx + 1 < len_:
            return
        rows, _ = self.win.getmaxyx()
        prev_s = self.get_rec(self.idx)
        next_s = self.get_rec(self.idx + 1)
        win_addstr(self.win, self.cur, 0, prev_s)
        if self.cur + 1 < rows:
            self.cur += 1
        else:
            self.win.move(0, 0)
            self.win.deleteln()
            self.cur = rows - 1
        win_addstr(self.win, self.cur, 0, next_s, attr=self.current_color)
        self.idx += 1
        self.win.refresh()
        self.refresh_deps()

    def scroll_up(self):
        len_ = self.len_recs()
        if not len_ or self.idx - 1 < 0:
            return
        prev_s = self.get_rec(self.idx)
        next_s = self.get_rec(self.idx - 1)
        win_addstr(self.win, self.cur, 0, prev_s)
        if self.cur > 0:
            self.cur -= 1
        else:
            self.win.move(0, 0)
            self.win.insdelln(1)
        win_addstr(self.win, self.cur, 0, next_s, attr=self.current_color)
        self.idx -= 1
        self.win.refresh()
        self.refresh_deps()

    def scroll_page_down(self):
        len_ = self.len_recs()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        idx = self.idx + rows
        if idx < len_:
            self.idx = idx
            self.refresh()
        else:
            idx = len_ - 1
            delta = idx - self.idx
            if not delta:
                self.scroll_bottom()
            elif self.cur + delta < rows:
                self.cur += delta
                self.idx = idx
                self.refresh()
            else:
                self.scroll_bottom()

    def scroll_page_up(self):
        len_ = self.len_recs()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        idx = self.idx - rows
        if not idx < 0:
            self.idx = idx
            self.refresh()
        else:
            self.scroll_top()
