import glob
import os
import readline
from functools import lru_cache
from getpass import getpass


@lru_cache(maxsize=1)
def glob_text(text: str):
    return glob.glob(os.path.expanduser(text) + '*')


def complete(text: str, state: int):
    'https://stackoverflow.com/questions/6656819/filepath-autocompletion-using-users-input'
    # return (glob.glob(text+'*')+[None])[state]
    # return (glob.glob(os.path.expanduser(text) + '*') + [None])[state]
    return (glob_text(text) + [None])[state]


def read_file(prompt: str):
    readline.set_completer_delims(' \t\n;')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete)
    while True:
        s = input(f'{prompt}')
        s = s.strip()
        if not s:
            continue
        if os.path.isfile(s):
            return s
        print(f'{s} is not a file')


def get_passwd(prompt: str) -> str:
    while True:
        passwd = getpass(prompt)
        if not passwd:
            continue
        return passwd
