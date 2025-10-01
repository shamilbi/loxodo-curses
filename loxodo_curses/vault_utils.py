import io
import os
import tempfile

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


def record2stream(fp, r: Record, passwd=False):
    fp.write(f'Title:\n{r.title}\n\n')
    fp.write(f'Group:\n{r.group}\n\n')
    fp.write(f'Username:\n{r.user}\n\n')
    if passwd:
        fp.write(f'Password:\n{r.passwd}\n\n')
    fp.write(f'URL:\n{r.url}\n\n')
    fp.write('Notes:\n')
    fp.write(f'{notes2str(r)}\n')


def file2record(fpath: str, r: Record, passwd=False):
    d = file2dict(fpath, passwd=passwd)
    r.title = d['title']
    r.group = d['group']
    r.user = d['user']
    if 'passwd' in d:
        r.passwd = d['passwd']
    r.url = d['url']
    r.notes = d['notes']


def file2dict(fpath: str, passwd=False) -> dict:
    with open(fpath, 'r', encoding='utf-8') as fp:
        return stream2dict(fp, passwd=passwd)


def stream2dict(fp, passwd=False) -> dict:
    d = {}
    step = 0
    find = {}
    find[i := 0] = ('Title:\n', 'title', 1)
    find[i := i + 1] = ('Group:\n', 'group', 1)
    find[i := i + 1] = ('Username:\n', 'user', 1)
    if passwd:
        find[i := i + 1] = ('Password:\n', 'passwd', 1)
    find[i := i + 1] = ('URL:\n', 'url', 1)
    find[i := i + 1] = ('Notes:\n', 'notes', 2)
    read_value = 0
    for line in fp:
        t = find[step]
        key = t[1]
        if read_value == 1:
            d[key] = line.rstrip()
            read_value = 0
            step += 1
            continue
        if read_value == 2:
            # read lines to the end
            if key not in d:
                d[key] = ''
            d[key] += line.rstrip() + '\r\n'
        if line != t[0]:
            continue
        if key not in d:
            d[key] = ''
        read_value = t[2]
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
        os.system(f'vim "{fpath}"')
        t2 = os.path.getmtime(fpath)
        if t1 != t2:
            file2record(fpath, r, passwd=passwd)  # r changed
            return True
    finally:
        if fd:
            os.close(fd)
            os.remove(fpath)
    return False
