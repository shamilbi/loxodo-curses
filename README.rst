loxodo-curses
=============

.. image:: https://badge.fury.io/py/loxodo-curses.svg
    :target: https://badge.fury.io/py/loxodo-curses

loxodo-curses is a curses frontend to `Password Safe`_ V3 compatible Password Vault.
A fork of `Loxodo`_.

Editing a file is performed with Vim, utilizing a temporary file in /dev/shm.
Launching a URL is accomplished using xdg-open.

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
    * S: Continue search
    * P: Change vault password
    * Ctrl-U: Copy Username to clipboard
    * Ctrl-P: Copy Password to clipboard
    * Ctrl-L: Copy URL to clipboard

.. _Password Safe: https://www.pwsafe.org/
.. _Loxodo: https://github.com/sommer/loxodo
