|pypi| |github|

loxodo-curses
=============

loxodo-curses is a curses frontend to `Password Safe`_ V3 compatible Password Vault.
A fork of `Loxodo`_.

Editing a record is done with Vim, using a temporary file located in /dev/shm. To launch a URL, xdg-open is used, while copying to the clipboard is handled by xsel.

To generate a password, just run the command ":read !pwmake 96" in Vim (pwmake is part of `libpwquality`_)
or ":read !diceware -d ' ' -s 2" (`diceware`_) or ":read !pwgen -s 25" (`pwgen`_).

The app includes a timeout feature that automatically closes it after 30 minutes of inactivity.

The current hotkeys are:
    * h: help screen
    * q, Esc: Quit the program
    * j, Down: Move selection down
    * k, Up: Move selection up
    * PgUp: Page up
    * PgDown: Page down
    * g, Home: Move to first item
    * G, End: Move to last item
    * Alt-{t,u,m,c,g}: Sort by title, user, modtime, created, group
    * Alt-{T,U,M,C,G}: Sort reversed
    * Delete: Delete current record
    * Insert: Insert record
    * d: Duplicate current record
    * e: Edit current record w/o password
    * E: Edit current record w/ password
    * L: Launch URL
    * s: Search records
    * P: Change vault password
    * Ctrl-U: Copy Username to clipboard
    * Ctrl-P: Copy Password to clipboard
    * Ctrl-L: Copy URL to clipboard
    * Ctrl-T: Copy TOTP to clipboard

.. |pypi| image:: https://badgen.net/pypi/v/loxodo-curses
          :target: https://pypi.org/project/loxodo-curses/
.. |github| image:: https://badgen.net/github/tag/shamilbi/loxodo-curses?label=github
            :target: https://github.com/shamilbi/loxodo-curses/
.. _Password Safe: https://www.pwsafe.org/
.. _Loxodo: https://github.com/sommer/loxodo
.. _libpwquality: https://github.com/libpwquality/libpwquality
.. _diceware: https://pypi.org/project/diceware/
.. _pwgen: https://sourceforge.net/projects/pwgen/files/pwgen/
