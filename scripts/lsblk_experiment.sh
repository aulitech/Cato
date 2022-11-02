#!/bin/bash
dir='../board_contents'
echo -e "We will list all the Hidden file in the current Directory $dir"
# find <path> <pattern> <action>
find ./board_contents -type f -name "*" -ls