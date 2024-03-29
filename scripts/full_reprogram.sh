#! /usr/bin/bash

boot_load_loc=/d/
auli_cato_loc=/d/

# Presence of boot_out.txt indicates board is in circuitPython Config
    FILE1=$auli_cato_loc/boot_out.txt

# Presence of these three files indicates default bootloader config
    BLFILE1=$boot_load_loc/CURRENT.UF2
    BLFILE2=$boot_load_loc/INDEX.HTM
    BLFILE3=$boot_load_loc/INFO_UF2.TXT

echo "BEGINNING UPLOAD PROCESS"

# Test that board is in bootloader mode, give user chance to reset board
    if test -f $FILE1; then
        echo BOARD MUST BE IN BOOTLOADER MODE. TAP RESET 2x
    fi
    # hang until boot_out is gone
    while [ -f "$FILE1" ]
    do
        sleep 1
        echo "    WAITING. TAP RESET 2x"
    done
    echo "    BOARD RESET"

# must wait for board to reconnect after power is cycled
    echo "WAITING FOR RECONNECTION AFTER POWER CYCLE"
    sleep 1
    while [ ! -d $boot_load_loc ]
    do
        sleep 1
        echo "    WAITING FOR AUTO-RECONNECT"
    done
    echo "    RECONNECTED"

# validate that board is in bootloader mode
    echo "VALIDATING CONFIG"
    # break with error if board contains boot_out.txt - generated by circuitPython
        if test -f "$FILE1"; then
            echo "    BOARD IS NOT IN BOOTLOADER MODE."
            echo "    LIKELY CAUSE: TAPPED BUTTON ONLY ONCE"
            exit 1
        fi
    # confirm that board has default bootloader config
        if [ -f "$BLFILE1" ] && [ -f "$BLFILE2" ] && [ -f "$BLFILE3" ]; then
            echo "    BOOTLOADER CONFIG VALIDATED"
        fi

# install the new bootloader
    echo "INSTALLING NEW BOOTLOADER"
    if test -f .bootloader/*.uf2; then
        echo "    FOUND FILE"
        echo "    COPYING .UF2"
        cp .bootloader/* "$boot_load_loc"
        echo "    DONE"
    fi

# install of new bootloader causes board to restart
# wait to reconnect
    echo "BOARD WILL RESTART"
    while [ ! -d $auli_cato_loc ]
    do
        sleep 1
        echo "    WAITING FOR AUTO-RECONNECT"
    done
    echo "    RECONNECTED"

# copy the source files
    echo "UPLOADING"
    echo "    COPYING LIBS"
    if ! test -d "$auli_cato_loc/lib"; then
        echo "        LIB FOLDER NOT FOUND -- CREATING LIB FOLDER"
        mkdir "$auli_cato_loc/lib"
    fi

    for dir in lib/**
    do
        dir=$dir
        echo "        COPYING ${dir}"
        cp -r $dir "$auli_cato_loc/lib"
        echo "            DONE"   
    done
    echo "    DONE WITH LIBS"

    echo "    COPYING WHITELISTED FILES"

    WHITELIST="./scripts/whitelist.txt"
    while read -r line
    do
        line=${line:0:-1}
        echo "    Copying $line to $auli_cato_loc"
        cp $line $auli_cato_loc
    done < "$WHITELIST"

    rm -f "$auli_cato_loc/code.py"