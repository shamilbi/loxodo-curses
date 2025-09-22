# from os import environ, system
# from os.path import exists, expanduser, join
import curses
import curses.ascii
import io
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from functools import partial
from signal import SIGINT, SIGTERM, signal
from threading import Timer
from typing import Callable

from . import __version__
from .utils import RowString, chunkstring, get_passwd, input_file, int2time, str2clipboard, win_addstr
from .vault import Record, Vault


class Win:
    def __init__(self, win, get_f, get_len_f, refresh_deps_f):
        '''
        s = self.get_f(idx)
        len_ = self.get_len_f()
        '''
        self.win = win
        self.get_f = get_f
        self.get_len_f = get_len_f
        self.refresh_deps_f = refresh_deps_f

        self.win.keypad(1)

        self.cur = 0  # cursor y
        self.idx = 0  # source index
        self.attr1 = curses.color_pair(1) | curses.A_BOLD

    def refresh(self):
        self.win.erase()
        len_ = self.get_len_f()
        if len_:
            rows, cols = self.win.getmaxyx()
            self.cur = min(self.cur, self.idx)
            for i in range(rows):
                idx = self.idx - self.cur + i
                if not idx < len_:
                    break
                s = self.get_f(idx)[:cols]
                if i == self.cur:
                    win_addstr(self.win, i, 0, s, attr=self.attr1)
                else:
                    win_addstr(self.win, i, 0, s)
            self.win.move(self.cur, 0)
        self.win.refresh()
        self.refresh_deps_f()

    def scroll_top(self):
        self.idx = self.cur = 0
        self.refresh()

    def scroll_bottom(self):
        len_ = self.get_len_f()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        self.cur = min(rows - 1, len_ - 1)
        self.idx = len_ - 1
        self.refresh()

    def scroll_down(self):
        len_ = self.get_len_f()
        if not len_ or not self.idx + 1 < len_:
            return
        rows, cols = self.win.getmaxyx()
        prev_s = self.get_f(self.idx)
        next_s = self.get_f(self.idx + 1)
        win_addstr(self.win, self.cur, 0, prev_s[:cols])
        if self.cur + 1 < rows:
            self.cur += 1
        else:
            self.win.move(0, 0)
            self.win.deleteln()
            self.cur = rows - 1
        win_addstr(self.win, self.cur, 0, next_s[:cols], attr=self.attr1)
        self.idx += 1
        self.win.refresh()
        self.refresh_deps_f()

    def scroll_up(self):
        len_ = self.get_len_f()
        if not len_ or self.idx - 1 < 0:
            return
        _, cols = self.win.getmaxyx()
        prev_s = self.get_f(self.idx)
        next_s = self.get_f(self.idx - 1)
        win_addstr(self.win, self.cur, 0, prev_s[:cols])
        if self.cur > 0:
            self.cur -= 1
        else:
            self.win.move(0, 0)
            self.win.insdelln(1)
        win_addstr(self.win, self.cur, 0, next_s[:cols], attr=self.attr1)
        self.idx -= 1
        self.win.refresh()
        self.refresh_deps_f()

    def scroll_page_down(self):
        len_ = self.get_len_f()
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
        len_ = self.get_len_f()
        if not len_:
            return
        rows, _ = self.win.getmaxyx()
        idx = self.idx - rows
        if not idx < 0:
            self.idx = idx
            self.refresh()
        else:
            self.scroll_top()


SORT: dict[str, Callable[[Record], tuple]] = {
    't': lambda r: (r.title.lower(), r.user.lower(), r.last_mod),
    'u': lambda r: (r.user.lower(), r.last_mod),
    'm': lambda r: (r.last_mod, r.title.lower(), r.user.lower()),
    'c': lambda r: (r.created, r.title.lower(), r.user.lower()),
    'g': lambda r: (r.group.lower(), r.last_mod),
}

HEADERS: dict[str, str] = {
    't': 'Title',
    'u': 'Username',
    'm': 'ModTime',
    'c': 'Created',
    'g': 'Group',
}

SORT_KEYS = ('t', 'u', 'm', 'c', 'g')
SORT_UP = '\u2191'
SORT_DOWN = '\u2193'


class Main:  # pylint: disable=too-many-instance-attributes
    def __init__(self, vault: Vault, fpath: str, screen):
        self.vault = vault
        self.vault_fpath = fpath
        self.screen = screen

        signal(SIGINT, self.shutdown)  # type: ignore[arg-type]
        signal(SIGTERM, self.shutdown)  # type: ignore[arg-type]

        self.screen.keypad(1)
        curses.curs_set(0)
        curses.noecho()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)

        self._filterstring = ''
        self.sortedby = '_'  # not defined
        self.sort()

        # title, user, last_mod, created, group
        self.row_string = RowString(35, 30, 19, 19, 0)

        self.create_windows()

        self.clear_thread: Timer | None = None  # thread to clear clipboard

    def sort(self, sortby: str = 't') -> bool:
        if not sortby or sortby == self.sortedby:
            return False
        if (key := sortby.lower()) not in SORT:
            return False
        sort_f = SORT[key]
        reverse = key != sortby
        self.sortedby = sortby
        self.records = [r for r in self.vault.records if self.filter_record(r)]
        self.records.sort(key=sort_f)
        if reverse:
            self.records.reverse()
        return True

    def sort2(self, sortby: str):
        idx = self.win.idx
        uuid = None
        if idx < self.records_len():
            r = self.records[idx]
            uuid = r.uuid  # to find the record after sorting
        if not self.sort(sortby):
            return
        # find new index of the record
        if uuid:
            g = (i for i, x in enumerate(self.records) if x.uuid == uuid)  # generator
            idx2 = next(g, 0)
        else:
            idx2 = 0
        self.win.idx = idx2
        self.refresh_all()

    def create_windows(self):
        '''
        ... header ...

        records ... | record |
            2/3        1/3
        '''
        maxy, maxx = (curses.LINES, curses.COLS)  # pylint: disable=no-member

        rows, cols = (maxy - 4, maxx)
        cols2 = min(cols // 3, 35)
        cols1 = cols - cols2

        win = self.screen.derwin(rows, cols1, 2, 0)
        self.win = Win(win, self.get_record_str, self.records_len, self.refresh_win_deps)

        self.win2 = self.screen.derwin(rows, cols2, 2, cols1)

        # status
        self.win3 = self.screen.derwin(2, cols, maxy - 2, 0)

    def refresh_win_deps(self):
        rows, cols = self.win2.getmaxyx()
        rows -= 2  # -borders
        cols -= 2  # -borders
        win = self.win2.derwin(rows, cols, 1, 1)
        win.erase()
        idx = self.win.idx
        if idx < len(self.records):
            r = self.records[idx]
            record2win(r, win)
        self.win2.refresh()

    def get_record(self, i: int) -> Record | None:
        len_ = len(self.records)
        if not i < len_:
            return None
        return self.records[i]

    def get_record_str(self, i: int) -> str:
        if not (r := self.get_record(i)):
            return ''
        return self.row_string.value(r.title, r.user, int2time(r.last_mod), int2time(r.created), r.group)

    def records_len(self) -> int:
        return len(self.records)

    def filter_record(self, record):
        if not self._filterstring:
            return True
        if record.title.lower().find(self._filterstring.lower()) >= 0:
            return True
        if record.group.lower().find(self._filterstring.lower()) >= 0:
            return True
        if record.user.lower().find(self._filterstring.lower()) >= 0:
            return True
        return False

    def create_header(self):
        headers = []
        key = self.sortedby.lower()
        reverse = key != self.sortedby
        for key2 in SORT_KEYS:
            title = HEADERS[key2]
            if key == key2:
                if reverse:
                    headers.append(f'{title}({SORT_UP}):')
                else:
                    headers.append(f'{title}({SORT_DOWN}):')
            else:
                headers.append(f'{title}:')
        return self.row_string.value(*headers)

    def refresh_all(self):
        self.screen.clear()

        header = self.vault.header
        s = f'Loxodo v{__version__} - {self.vault_fpath}, {header.last_save} (h - Help)'
        _, cols = self.win.win.getmaxyx()
        win_addstr(self.screen, 0, 0, s[:cols])
        win_addstr(self.screen, 1, 0, self.create_header())
        self.screen.refresh()

        self.win.refresh()

        self.win2.erase()
        self.win2.box()
        self.refresh_win_deps()

        ch = curses.ACS_HLINE
        self.win3.border(' ', ' ', ch, ' ', ch, ch, ' ', ' ')
        self.win3.refresh()

    def run(self):
        self.input_loop()

    def handle_alt_key(self):
        # https://stackoverflow.com/a/22362849
        self.screen.nodelay(True)
        ch = self.screen.getch()  # get the key pressed after ALT
        self.screen.nodelay(False)
        if ch == -1:
            self.shutdown()
        if (ch2 := chr(ch)).lower() in SORT_KEYS:
            self.sort2(ch2)

    def status(self, s: str):
        win_addstr(self.win3, 1, 0, s)
        self.win3.refresh()

    def run_url(self):
        if not (r := self.get_record(self.win.idx)):
            return
        if not r.url:
            return
        try:
            if shutil.which("xdg-open"):
                subprocess.run(['xdg-open', r.url], check=False)
            else:
                webbrowser.open(r.url)
        except ImportError:
            self.status(f'Could not load python module "webbrowser" for {r.url=}')

    def user2clipboard(self):
        if not (r := self.get_record(self.win.idx)):
            return
        if r.user:
            str2clipboard(r.user)
            self.status('Username copied to clipboard')
        else:
            self.status('Username is empty')

    def passwd2clipboard(self):
        if not (r := self.get_record(self.win.idx)):
            return
        if r.passwd:
            t = self.clear_thread
            if t and t.is_alive():
                t.cancel()
            str2clipboard(r.passwd)
            t = self.clear_thread = Timer(10, str2clipboard, args=[''])
            t.start()
            self.status('Password copied to clipboard')
        else:
            self.status('Password is empty')

    def input_loop(self):  # pylint: disable=too-many-branches
        self.refresh_all()
        while True:
            try:
                char_ord = self.screen.getch()
                char = chr(char_ord)

                if char_ord == curses.ascii.ESC:  # Esc
                    self.handle_alt_key()
                # elif char.upper() == 'Q' or char_ord == curses.ascii.ESC:  # Esc or Q
                elif char.upper() == 'Q':
                    self.shutdown()
                elif char.upper() == 'J' or char_ord == curses.KEY_DOWN:  # Down or J
                    self.win.scroll_down()
                elif char.upper() == 'K' or char_ord == curses.KEY_UP:  # Up or K
                    self.win.scroll_up()
                elif char == 'g' or char_ord == curses.KEY_HOME:  # Move to top
                    self.win.scroll_top()
                elif char == 'G' or char_ord == curses.KEY_END:  # Move to last item
                    self.win.scroll_bottom()
                elif char_ord == curses.KEY_NPAGE:  # Page down
                    self.win.scroll_page_down()
                elif char_ord == curses.KEY_PPAGE:  # Page up
                    self.win.scroll_page_up()
                elif char == 'e':
                    self.launch_editor()  # not using curses
                    self.screen.refresh()
                elif char == 'E':
                    self.launch_editor(passwd=True)  # not using curses
                    self.screen.refresh()
                elif char.upper() == 'H':  # Print help screen
                    self.print_help_screen()
                    self.refresh_all()
                elif char_ord == 12:  # ^L
                    self.run_url()
                elif char_ord == 21:  # ^U
                    self.user2clipboard()
                elif char_ord == 16:  # ^P
                    self.passwd2clipboard()
                else:
                    name = curses.keyname(char_ord).decode('utf-8')
                    self.status(f'{char_ord=}, {name=}')
            except curses.error:
                pass

    def shutdown(self):
        sys.exit(0)

    def launch_editor(self, passwd=False):
        idx = self.win.idx
        if not idx < len(self.records):
            return
        r = self.records[idx]
        curses.endwin()
        fd = None
        fpath = ''
        try:
            fd, fpath = tempfile.mkstemp(dir='/dev/shm', text=True)
            # t1 = os.path.getmtime(fpath)
            record2file(r, fpath, passwd=passwd)
            os.system(f'vim "{fpath}"')
            # t2 = os.path.getmtime(fpath)
        finally:
            if fd:
                os.close(fd)
                os.remove(fpath)

    def print_help_screen(self):
        header = "Help information:"
        help_ = [
            ("h", "This help screen"),
            ("q, Esc", "Quit the program"),
            ("e", "Edit current record w/o password"),
            ("E", "Edit current record w/ password"),
            ("j, Down", "Move selection down"),
            ("k, Up", "Move selection up"),
            ("PgUp", "Page up"),
            ("PgDown", "Page down"),
            ("g, Home", "Move to first item"),
            ("G, End", "Move to last item"),
            ("Alt_{t,u,m,c,g}", "Sort by title, user, modtime, created, group"),
            ("Alt_{T,U,M,C,G}", "Sort reversed"),
            ("Ctrl_L", "Run URL"),
            ("Ctrl_U", "Copy Username to clipboard"),
            ("Ctrl_P", "Copy Password to clipboard"),
        ]
        win_text(self.screen, header, help_)


def notes2str(r: Record) -> str:
    s = ''
    if r.notes:
        s = r.notes.rstrip().replace('\r\n', '\n')
        s = s.replace('\t', ' ' * 4)
    return s


def record2str(r: Record, passwd=False) -> str:
    with io.StringIO() as fp:
        fp.write(f'Title:\n{r.title}\n\n')
        fp.write(f'Group:\n{r.group}\n\n')
        fp.write(f'Username:\n{r.user}\n\n')
        if passwd:
            fp.write(f'Password:\n{r.passwd}\n\n')
        fp.write(f'URL:\n{r.url}\n\n')
        fp.write('Notes:\n')
        if s := notes2str(r):
            fp.write(f'{s}\n')
        return fp.getvalue()


def record2win(r: Record, win):
    rows, cols = win.getmaxyx()
    row = -1
    for line in record2str(r).splitlines():
        for s in chunkstring(line, cols):
            row += 1
            if not row < rows:
                return
            win_addstr(win, row, 0, s)


def record2file(r: Record, fpath: str, passwd=False):
    with open(fpath, 'w', encoding='utf-8') as fp:
        fp.write(record2str(r, passwd=passwd))


def win_text(screen, header: str, help_: list[tuple[str, str]]):  # pylint: disable=too-many-locals
    '''
    help_ = [
        (key1, help1),
        (key2, help2),
        ...
    ]
    '''
    footer = "Press any key to continue..."

    lmax = max(len(i[0]) for i in help_)  # (lmax) - help

    def iter_help():
        for i, j in help_:
            yield f'{i:<{lmax}} - {j}'  # keys - help

    rows = len(help_) + 1  # footer=1
    rows2 = rows + 2  # border=2
    cols = max(len(header), max(len(i) for i in iter_help()), len(footer))
    cols2 = cols + 2  # border=2

    max_rows, max_cols = screen.getmaxyx()
    rows2 = min(rows2, max_rows)
    cols2 = min(cols2, max_cols)
    cols = cols2 - 2
    header = header[:cols2]
    y = (max_rows - rows2) // 2
    x = (max_cols - cols2) // 2

    win = screen.derwin(rows2, cols2, y, x)
    win.keypad(1)
    win.erase()
    win.box()

    row = 0
    x = (cols2 - len(header)) // 2
    win_addstr(win, row, x, header[: cols2 - x])
    col = 1
    for s in iter_help():
        row += 1
        win_addstr(win, row, col, s[:cols])
    row += 1
    win_addstr(win, row, col, footer[:cols])

    # Wait for any key press
    win.getch()

    # https://stackoverflow.com/questions/2575409/how-do-i-delete-a-curse-window-in-python-and-restore-background-window
    win.erase()
    del win
    screen.touchwin()


def main2(vault: Vault, fpath: str, screen):
    app = Main(vault, fpath, screen)
    app.run()


def main():
    try:
        fpath = input_file('Pwsafe file: ')
        passwd = get_passwd('Password: ')
        vault = Vault(passwd.encode('latin1', 'replace'), fpath)
        main2_ = partial(main2, vault, fpath)
        curses.wrapper(main2_)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
