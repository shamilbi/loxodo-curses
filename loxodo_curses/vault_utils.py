import io
import os
import subprocess
import tempfile
from typing import Callable

from .vault import Record


def notes2str(r: Record) -> str:
    s = ''
    if r.notes:
        s = r.notes.rstrip().replace('\r\n', '\n')
        s = s.replace('\t', ' ' * 4)
    return s


def record2str(r: Record, passwd=False) -> str:
    with io.StringIO() as fp:
        record2stream(fp, r, passwd=passwd)
        return fp.getvalue()


FIELDS: list[tuple[str, str, Callable[[Record], str], int]] = [
    # id, title, r -> str, type
    ('title', 'Title', lambda r: r.title, 1),
    ('group', 'Group', lambda r: r.group, 1),
    ('user', 'Username', lambda r: r.user, 1),
    ('passwd', 'Password', lambda r: r.passwd, 1),
    ('url', 'URL', lambda r: r.url, 1),
    ('notes', 'Notes', notes2str, 2),
]


def record2stream(fp, r: Record, passwd=False):
    first = True
    for id_, s, f, _ in FIELDS:
        if id_ == 'passwd' and not passwd:
            continue
        if first:
            first = False
        else:
            fp.write('\n')
        fp.write(f'{s}:\n{f(r)}\n')


def file2record(fpath: str, r: Record, passwd=False):
    d = file2dict(fpath, passwd=passwd)
    r.title = d['title']
    r.group = d['group']
    r.user = d['user']
    if 'passwd' in d:
        r.passwd = d['passwd']
    r.url = d['url']
    r.notes = d['notes'].rstrip()


def file2dict(fpath: str, passwd=False) -> dict:
    with open(fpath, 'r', encoding='utf-8') as fp:
        return stream2dict(fp, passwd=passwd)


def stream2dict(fp, passwd=False) -> dict:
    steps = []
    for id_, s, _, type_ in FIELDS:
        if id_ == 'passwd' and not passwd:
            continue
        steps.append((f'{s}:\n', id_, type_))
    d = {}
    step = 0
    read_value = 0
    for line in fp:
        s, id_, type_ = steps[step]
        if read_value == 1:
            d[id_] = line.rstrip()
            read_value = 0
            step += 1
            if step >= len(steps):
                break
            continue
        if read_value == 2:
            # read lines to the end
            d[id_] += line.rstrip() + '\r\n'
            continue
        if line != s:
            continue
        if id_ not in d:
            d[id_] = ''
        read_value = type_
    return d


def record2file(r: Record, fpath: str, passwd=False):
    with open(fpath, 'w', encoding='utf-8') as fp:
        record2stream(fp, r, passwd=passwd)


def edit_record(r: Record, passwd: bool = False) -> bool:
    fd = None
    fpath = ''
    try:
        fd, fpath = tempfile.mkstemp(dir='/dev/shm', text=True)
        record2file(r, fpath, passwd=passwd)
        t1 = os.path.getmtime(fpath)
        subprocess.run(['vim', fpath], check=False)
        t2 = os.path.getmtime(fpath)
        if t1 != t2:
            file2record(fpath, r, passwd=passwd)  # r changed
            return True
    finally:
        if fd:
            os.close(fd)
            os.remove(fpath)
    return False
