from __future__ import annotations

from collections.abc import Iterable

from curses_utils2.record import RecordProto, Text2Field

from .vault import Record


class Record2(RecordProto):
    'a wrapper for edit Record'

    def __init__(self, r: Record, passwd: bool = False):
        self.r = r
        self.passwd = passwd  # show password

    def form_fields(self) -> Iterable[tuple[str, str, str, Text2Field]]:
        'id, title, value, type'
        yield ('title', 'Title', self.r.title, Text2Field.SINGLE)
        yield ('group', 'Group', self.r.group, Text2Field.SINGLE)
        yield ('user', 'Username', self.r.user, Text2Field.SINGLE)
        if self.passwd:
            yield ('passwd', 'Password', self.r.passwd, Text2Field.SINGLE)
        yield ('url', 'URL', self.r.url, Text2Field.SINGLE)
        yield ('notes', 'Notes', self.r.notes, Text2Field.MULTI)

    def set_dict(self, d: dict) -> bool:
        for name, value in d.items():
            match name:
                case 'title':
                    self.r.title = value
                case 'group':
                    self.r.group = value
                case 'user':
                    self.r.user = value
                case 'passwd':
                    if self.passwd:
                        self.r.passwd = value
                case 'url':
                    self.r.url = value
                case 'notes':
                    self.r.notes = value
        return True
