#!/bin/bash

main2() {
    if [[ $(command -v pex.sh) ]]; then
        # local pex
        pex=pex.sh
    elif [[ $(command -v pex) ]]; then
        pex=pex
    else
        echo "exe not found: pex"
        return 1
    fi

    local opts=(
        -o dist/loxodo-curses.pex
        --project .
        --python python3.13
        -e loxodo_curses.__main__:main
        --python-shebang "/usr/bin/env python3"
    )
    "$pex" "${opts[@]}"
}

main() {
    (
        # out of contrib/
        cd "$(dirname "$0")"/.. || exit 1
        main2
    )
}

main "$@"
