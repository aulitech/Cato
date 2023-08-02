#! /usr/bin/bash

# This script is designed to update the contents of "DragAndDrop_ToProgram"
drag_drop_loc="DragAndDrop_ToProgram/"

# reset the release folder
rm -rf $drag_drop_loc
mkdir $drag_drop_loc

WHITELIST="./scripts/whitelist.txt"
    while read -r line
    do
        line=${line:0:-1}
        echo "    Copying $line to Drag/Drop Folder"
        cp $line $drag_drop_loc
    done < "$WHITELIST"
