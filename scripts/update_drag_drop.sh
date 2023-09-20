#! /usr/bin/bash

# This script is designed to update the contents of "DragAndDrop_ToProgram"
release_loc="release/"
uf2_loc="release/firmware/"
code_loc="./release/drag_and_drop/"

# reset the release folder
rm -rf $release_loc

mkdir $release_loc
mkdir $uf2_loc
mkdir $code_loc

WHITELIST="./scripts/whitelist.txt"
    while read -r line
    do
        line=${line:0:-1}
        echo "    Copying $line to Drag/Drop Folder"
        cp $line $code_loc
    done < "$WHITELIST"

# Copy Libs
cp -r "./lib" $code_loc

# Copy bootloader
cp ./.bootloader/* $uf2_loc
