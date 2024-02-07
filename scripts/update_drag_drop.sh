#! /usr/bin/bash

# This script is designed to update the contents of "DragAndDrop_ToProgram"
release_loc="release/"

# reset the release folder
rm -rf $release_loc

mkdir $release_loc

WHITELIST="./scripts/whitelist.txt"
    while read -r line
    do
        line=${line:0:-1}
        echo "    Copying $line to $release_loc"
        cp $line $release_loc
    done < "$WHITELIST"

# Copy Libs
cp -r "./lib" $release_loc
