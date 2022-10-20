#!/bin/bash

auli_cato_loc=/d/
echo "Checking connection"
while [ ! -d $auli_cato_loc ]
do
    sleep 1
    echo "    Waiting for connection"
done

    echo "    COPYING SOURCE FILES"
    for thing in $(dir ./board_contents/* -a)
    do
        f="$thing"
        #echo "        DECIDING ABOUT ${f}"
        if test -f "$f"; then
            echo "        COPYING ${f}"
            cp "$f" "$auli_cato_loc"
            echo "            DONE"
        fi
    done
    if test -f "./board_contents/.env"; then
        echo "        COPYING .env"
        cp board_contents/.env "$auli_cato_loc"
        echo "            DONE"
    fi
    echo "    DONE WITH .PY FILES"
    echo "UPLOAD COMPLETE"