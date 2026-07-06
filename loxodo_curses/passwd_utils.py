import time
from getpass import getpass


def get_passwd(prompt: str) -> str:
    while True:
        passwd = getpass(prompt)
        if not passwd:
            continue
        return passwd


def get_new_passwd(oldpasswd: str) -> str | None:
    print('Changing password (to cancel press ^C)')

    def failed():
        print('Abort')
        time.sleep(0.5)

    try:
        passwd = get_passwd('Old password: ')
        if passwd != oldpasswd:
            return failed()
        passwd = get_passwd('New password: ')
        passwd2 = get_passwd('Repeat new password: ')
        if passwd != passwd2:
            return failed()
        return passwd
    except KeyboardInterrupt:
        return failed()
