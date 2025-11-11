import binascii
import curses
import curses.ascii
import os
import re
import shutil
import subprocess
import webbrowser
from collections.abc import Callable
from contextlib import contextmanager
from functools import partial
from signal import SIGINT, signal
from threading import Event, Timer

import mintotp  # type: ignore[import-untyped]

from . import __version__
from .curses_utils import App, List, ask_delete, win_addstr, win_help
from .utils import (
    FilterString,
    RowString,
    StopThread,
    chunkstring,
    get_new_passwd,
    get_passwd,
    input_file,
    int2time,
    str2clipboard,
)
from .vault import BadPasswordError, Record, Vault, duplicate_record
from .vault_utils import edit_record, record2str

HELP = [
    ("h", "This help screen"),
    ("q, Esc", "Quit the program"),
    ("j, Down", "Move selection down"),
    ("k, Up", "Move selection up"),
    ("PgUp", "Page up"),
    ("PgDown", "Page down"),
    ("g, Home", "Move to first item"),
    ("G, End", "Move to last item"),
    ("Alt-{t,u,m,c,g}", "Sort by title, user, modtime, created, group"),
    ("Alt-{T,U,M,C,G}", "Sort reversed"),
    ("Delete", "Delete current record"),
    ("Insert", "Insert record"),
    ("d", "Duplicate current record"),
    ("e", "Edit current record w/o password"),
    ("E", "Edit current record w/ password"),
    ("L", "Launch URL"),
    ("s", "Search records"),
    ("P", "Change vault password"),
    ("Ctrl-U", "Copy Username to clipboard"),
    ("Ctrl-P", "Copy Password to clipboard"),
    ("Ctrl-L", "Copy URL to clipboard"),
    ("Ctrl-T", "Copy TOTP to clipboard"),
]

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


class Main(App):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    def __init__(self, vault: Vault, fpath: str, passwd: bytes, screen):
        super().__init__(screen)

        self.vault = vault
        self.vault_fpath = fpath
        self.vault_passwd = passwd

        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)

        self.filter = FilterString()
        self.sort()

        # title, user, last_mod, created, group
        self.row_string = RowString(35, 30, 19, 19, 0)

        self.create_windows()

        self.clear_thread: Timer | None = None  # thread to clear clipboard

        self.stop = Event()
        self.stop_thread = StopThread(30 * 60, self.stop)  # 30 min
        self.stop_thread.start()

    def sort(self, sortby: str = 't') -> bool:
        if not sortby:
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
        Loxodo v...file...time...
        Search: ...
        ... header ...
        records ... | record |
            2/3        1/3
        ---------------------
        status ...
        '''
        maxy, maxx = self.screen_size

        rows, cols = (maxy - 6, maxx)
        cols2 = min(cols // 3, 35)
        cols1 = cols - cols2
        if no_win2 := cols1 < sum(self.row_string.widths[:2]):
            cols1 = cols

        prompt = self.prompt_search = ' Search: '
        len_ = len(prompt)
        self.win_search = self.screen.derwin(1, maxx - len_, 1, len_)

        win = self.screen.derwin(rows, cols1 - 3, 4, 2)
        self.win = List(win, self, current_color=curses.color_pair(1) | curses.A_BOLD)

        if no_win2:
            self.win2 = None
        else:
            self.win2 = self.screen.derwin(maxy - 3, cols2, 2, cols1)

        # status
        self.win3 = self.screen.derwin(1, maxx, maxy - 1, 0)

    def refresh_win_deps(self):
        if not self.win2:
            return
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

    def del_record(self, i: int):
        if not (r := self.get_record(i)):
            return
        if ask_delete(self.screen, color=curses.color_pair(2)):
            del self.records[i]
            self.vault.records.remove(r)
            self.vault.write_to_file(self.vault_fpath, self.vault_passwd)
        self.win.refresh()

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
        return self.filter.found(record.title, record.group, record.user)

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
        s = f' Loxodo v{__version__} - {self.vault_fpath}, {header.last_save} (h - Help)'
        win_addstr(self.screen, 0, 0, s)

        win_addstr(self.screen, 1, 0, self.prompt_search)
        self.screen.refresh()

        self.win_search.erase()
        win_addstr(self.win_search, 0, 0, self.filter.filter_string)
        self.win_search.refresh()

        maxy, maxx = self.screen_size
        win = self.screen.derwin(maxy - 3, maxx, 2, 0)
        win.erase()
        win_addstr(win, 1, 2, self.create_header())
        win.box()
        win.refresh()

        self.win.refresh()

        if self.win2:
            self.win2.erase()
            self.win2.border(0, 0, 0, 0, curses.ACS_TTEE, 0, curses.ACS_BTEE, 0)
            self.win2.refresh()

        self.refresh_win_deps()

    def run(self):
        self.refresh_all()
        self.input_loop()

    def handle_alt_key(self, ch: int):
        self.stop_thread.reset()
        if (ch2 := chr(ch)).lower() in SORT_KEYS:
            self.sort2(ch2)

    def status(self, s: str):
        win = self.win3
        win.erase()
        win_addstr(win, 0, 1, s)
        win.refresh()

    def search(self):
        curses.endwin()
        old = signal(SIGINT, self.orig_sigint)
        try:
            self.filter.set(input(self.prompt_search.lstrip()))
            self.screen.refresh()
            win_addstr(self.win_search, 0, 0, self.filter.filter_string)
            self.sort2(self.sortedby)
        except KeyboardInterrupt:
            self.screen.refresh()
        finally:
            signal(SIGINT, old)

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

    def shutdown(self, *_):
        self.stop.set()
        t = self.clear_thread
        if t and t.is_alive():
            t.cancel()
        super().shutdown(*_)

    def clear_clipboard(self):
        str2clipboard('')
        self.status('')

    @contextmanager
    def check_clipboard(self):
        t = self.clear_thread
        if t and t.is_alive():
            t.cancel()
        try:
            yield
        finally:
            t = self.clear_thread = Timer(10, self.clear_clipboard)
            t.start()

    def passwd2clipboard(self):
        if not (r := self.get_record(self.win.idx)):
            return
        if r.passwd:
            with self.check_clipboard():
                str2clipboard(r.passwd)
            self.status('Password copied to clipboard')
        else:
            self.status('Password is empty')

    def totp2clipboard(self):
        if not (r := self.get_record(self.win.idx)):
            return
        passwd2 = r.passwd.replace(' ', '')  # A B -> AB
        m = re.match(r'([a-z0-9]+):', passwd2, flags=re.A + re.I)  # sha1:....
        if m:
            digest = m.group(1)
            passwd2 = passwd2[len(digest) + 1 :]
        else:
            digest = 'sha1'
        try:
            totp = mintotp.totp(passwd2, digest=digest)
            with self.check_clipboard():
                str2clipboard(totp)
            totp2 = ' '.join([totp[i : i + 3] for i in range(0, len(totp), 3)])  # 123 456 ...
            self.status(f'TOTP({digest}): {totp2}')
        except (RuntimeError, binascii.Error, ValueError):
            # ValueError: totp: bad digest
            self.status('TOTP error')

    def url2clipboard(self):
        if not (r := self.get_record(self.win.idx)):
            return
        if r.url:
            str2clipboard(r.url)
            self.status('URL copied to clipboard')
        else:
            self.status('URL is empty')

    def input_loop(self):  # pylint: disable=too-many-branches,too-many-statements
        for char_ord in self.getch():
            self.stop_thread.reset()
            char = chr(char_ord)

            if char_ord == curses.KEY_DC:  # delete
                self.del_record(self.win.idx)
            elif char_ord == curses.KEY_IC:  # insert
                self.insert_record(self.win.idx)
            elif self.win.handle_input(char_ord):
                pass
            elif char == 'e':
                self.edit_record(self.win.idx)  # not using curses
            elif char == 'd':
                self.duplicate_record(self.win.idx)  # not using curses
            elif char == 's':
                self.search()
            elif char == 'E':
                self.edit_record(self.win.idx, passwd=True)  # not using curses
            elif char == 'P':
                self.change_vault_passwd()  # not using curses
            elif char == 'L':
                self.run_url()
            elif char.upper() == 'H':  # Print help screen
                win_help(self.win.win, HELP)
                self.refresh_all()
            elif char_ord == 12:  # ^L
                self.url2clipboard()
            elif char_ord == 21:  # ^U
                self.user2clipboard()
            elif char_ord == 16:  # ^P
                self.passwd2clipboard()
            elif char_ord == 20:  # ^T
                self.totp2clipboard()
            else:
                name = curses.keyname(char_ord).decode('utf-8')
                self.status(f'{char_ord=}, {name=}')

    def edit_record(self, i: int, passwd=False):
        if not (r := self.get_record(i)):
            return
        curses.endwin()
        if edit_record(r, passwd=passwd):
            self.vault.write_to_file(self.vault_fpath, self.vault_passwd)
        self.win.refresh()

    def change_vault_passwd(self):
        curses.endwin()
        old = signal(SIGINT, self.orig_sigint)
        try:
            passwd = get_new_passwd(self.vault_passwd.decode('utf-8'))
            if passwd:
                bytes_ = passwd.encode('utf-8')
                print('Wait ...')
                self.vault.write_to_file(self.vault_fpath, bytes_)
                self.vault_passwd = bytes_
        finally:
            signal(SIGINT, old)
        self.screen.refresh()

    def duplicate_record(self, i: int):
        if not (r := self.get_record(i)):
            return
        curses.endwin()
        r2 = duplicate_record(r)
        if edit_record(r2, passwd=True):
            self.vault.records.append(r2)
            self.vault.write_to_file(self.vault_fpath, self.vault_passwd)
            self.records.insert(i, r2)
        self.win.refresh()

    def insert_record(self, i: int):
        r = Record.create()
        curses.endwin()
        if edit_record(r, passwd=True):
            self.vault.records.append(r)
            self.vault.write_to_file(self.vault_fpath, self.vault_passwd)
            self.records.insert(i, r)
        self.win.refresh()


def record2win(r: Record, win):
    rows, cols = win.getmaxyx()
    row = -1
    for line in record2str(r).splitlines():
        for s in chunkstring(line, cols):
            row += 1
            if not row < rows:
                return
            win_addstr(win, row, 0, s)


def main2(vault: Vault, fpath: str, passwd: bytes, screen):
    app = Main(vault, fpath, passwd, screen)
    app.run()


def main():
    try:
        fpath = input_file('Pwsafe file: ')
        if not os.path.exists(fpath):
            print(f'New vault: {fpath}')
        while True:
            try:
                passwd: bytes = get_passwd('Password: ').encode('utf-8')
                if os.path.isfile(fpath):
                    vault = Vault(passwd, fpath)
                else:
                    vault = Vault.create(passwd, fpath)
                break
            except BadPasswordError:
                print('bad password!')
                continue
    except KeyboardInterrupt:
        return
    main2_ = partial(main2, vault, fpath, passwd)
    curses.wrapper(main2_)


if __name__ == '__main__':
    main()
