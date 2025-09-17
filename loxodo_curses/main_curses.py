# from os import environ, system
# from os.path import exists, expanduser, join
import curses
import curses.ascii
import sys
from functools import partial
from signal import SIGINT, SIGTERM, signal

from . import __version__
from .utils import get_passwd, read_file
from .vault import Vault


class Win:
    def __init__(self, win, get_f, get_len_f):
        '''
        s = self.get_f(idx)
        len_ = self.get_len_f()
        '''
        self.win = win
        self.get_f = get_f
        self.get_len_f = get_len_f

        self.win.keypad(1)

        self.cur = 0  # cursor y
        self.idx = 0  # source index

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
                    self.win.addstr(i, 0, s, curses.color_pair(1) | curses.A_BOLD)
                else:
                    self.win.addstr(i, 0, s)
            self.win.move(self.cur, 0)
        self.win.refresh()

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
        self.win.addstr(self.cur, 0, f"{prev_s}"[:cols])
        if self.cur + 1 < rows:
            self.cur += 1
        else:
            self.win.move(0, 0)
            self.win.deleteln()
            self.cur = rows - 1
        self.win.addstr(self.cur, 0, f"{next_s}"[:cols], curses.color_pair(1) | curses.A_BOLD)
        self.idx += 1
        self.win.refresh()

    def scroll_up(self):
        len_ = self.get_len_f()
        if not len_ or self.idx - 1 < 0:
            return
        _, cols = self.win.getmaxyx()
        prev_s = self.get_f(self.idx)
        next_s = self.get_f(self.idx - 1)
        self.win.addstr(self.cur, 0, f"{prev_s}"[:cols])
        if self.cur > 0:
            self.cur -= 1
        else:
            self.win.move(0, 0)
            self.win.insdelln(1)
        self.win.addstr(self.cur, 0, f"{next_s}"[:cols], curses.color_pair(1) | curses.A_BOLD)
        self.idx -= 1
        self.win.refresh()

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


class Main:
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
        self.sort_function = lambda e1: (e1.title.lower(), e1.user.lower(), e1.last_mod)
        self.records = [r for r in self.vault.records if self.filter_record(r)]
        self.records.sort(key=self.sort_function)

        win = self.screen.derwin(curses.LINES - 2, curses.COLS, 2, 0)  # pylint: disable=no-member
        self.win = Win(win, self.get_record, self.records_len)

    def get_record(self, i):
        len_ = len(self.records)
        if i < 0 and i < -len_ or i >= 0 and not i < len_:
            return None
        return self.records[i].title

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

    def refresh_all(self):
        self.screen.clear()
        header = self.vault.header
        s = f'Loxodo v{__version__} - {self.vault_fpath}, {header.last_save} (h - Help)'
        _, cols = self.win.win.getmaxyx()
        self.screen.addstr(0, 0, s[:cols])
        self.screen.refresh()
        self.win.refresh()

    def run(self):
        self.input_loop()

    def input_loop(self):
        self.refresh_all()
        while True:
            try:
                char_ord = self.screen.getch()
                char = chr(char_ord)

                if char.upper() == 'Q' or char_ord == curses.ascii.ESC:  # Esc or Q
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
                # elif char.upper() == 'E':
                #     self.launch_editor()  # not using curses
                #     self.screen.refresh()
                elif char.upper() == 'H':  # Print help screen
                    self.print_help_screen()
                    self.refresh_all()
            except curses.error as e:
                curses.endwin()
                print('[-] Invalid keypress detected.')
                print(e)
                input('Press Enter to continue ...')

    def shutdown(self):
        sys.exit(0)

    # def launch_editor(self):
    #     curses.endwin()
    #     editor = environ.get('EDITOR')
    #     if editor is None:  # Default editors
    #         if sys.platform == 'win32':
    #             editor = 'notepad.exe'
    #         elif sys.platform == 'darwin':
    #             editor = 'nano'
    #         elif 'linux' in sys.platform:
    #             editor = 'vi'
    #     system(f"{editor} {fpath}")

    def print_help_screen(self):
        header = "Help information:"
        help_ = [
            ("h", "This help screen"),
            ("q, Esc", "Quit the program"),
            # ("e", "Edit current record"),
            ("j, Down", "Move selection down"),
            ("k, Up", "Move selection up"),
            ("PgUp", "Page up"),
            ("PgDown", "Page down"),
            ("g, Home", "Move to first item"),
            ("G, End", "Move to last item"),
        ]
        win_text(self.screen, header, help_)


def win_text(screen, header: str, help_: list[tuple[str, str]]):
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
    win.addstr(row, x, header[: cols2 - x])
    col = 1
    for s in iter_help():
        row += 1
        win.addstr(row, col, s[:cols])
    row += 1
    win.addstr(row, col, footer[:cols])

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
        fpath = read_file('Pwsafe file: ')
        passwd = get_passwd('Password: ')
        vault = Vault(passwd.encode('latin1', 'replace'), fpath)
        main2_ = partial(main2, vault, fpath)
        curses.wrapper(main2_)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
