#!/bin/bash

device="Cato"
boot_mount="XIAO-SENSE"
auli_mount="AULI_CATO"
windows_mount="/d/"
WHITELIST="./scripts/whitelist.txt"

await_test () {
    # Prompt if test passes
    [ $2 "$3" ] && echo -e "$1"

    # Wait for test to pass
    ct=0
    while [ $2 "$3" ]
    do
        sleep 1
        ct=$((ct+1))
        echo -n "$ct "
        [ $ct -gt $4 ] && echo -e "\nTimed out. $5" && exit 1
    done
}

# osx or windows?

os=$(uname -s) || $(ver) || true
if [ "$os" == "" ]; then
    echo "Failed. Can't determine OS."
    exit
fi

if [ "$os" == "Darwin" ]; then
    os="OSX"
    auli_cato_loc="/Volumes/$auli_mount"
    boot_load_loc="/Volumes/$boot_mount"
else
    os="WINDOWS"
    auli_cato_loc=$windows_mount
    boot_load_loc=$windows_mount
fi

echo Installing Firmware on $boot_load_loc and Application on $auli_cato_loc

# Presence of boot_out.txt indicates board is in circuitPython Config
FILE1=$auli_cato_loc/boot_out.txt

# Presence of these three files indicates default bootloader config
BLFILE1=$boot_load_loc/CURRENT.UF2
BLFILE2=$boot_load_loc/INDEX.HTM
BLFILE3=$boot_load_loc/INFO_UF2.TXT

# Make sure update files are present

[ ! -f .bootloader/*.uf2 ] && echo "Firmare not found." && exit 1

[ ! -f $WHITELIST ] && echo "Application Files not found." && exit 1

echo -e "\n\nStarting Firmware Update.\nPlease ensure that $device is connected via USB.\n"

# Test that board is in bootloader mode, give user chance to reset board

await_test "Enter Firmware Update Mode by tapping the reset button twice." "! -f" "$BLFILE3" 30 "$device is not in Firmware Update Mode."

# install the new bootloader
echo -n "Downloading new firmware..."
cp .bootloader/* "$boot_load_loc"
echo "Done.\n"

# install of bootloader causes board to restart
# wait to reconnect

await_test "Waiting for $device to restart." "! -d" "$auli_cato_loc" 30 "$device not ready."

#
echo "Downloading Libraries"
echo "    Copying Libraries"

# Make sure lib directory exists
[ ! -d "$auli_cato_loc/lib" ] && mkdir "$auli_cato_loc/lib"

for dir in lib/**
do
    dir=$dir
    echo "        ${dir}"
    cp -r $dir "$auli_cato_loc/lib"
done

echo Installing $device Application files on $auli_cato_loc
await_test "Checking for $device." "! -d" "$auli_cato_loc" 30 "Please reset $device with a single tap."

echo "Copying Files:"
while read -r line
do
    line=`echo $line | sed 's/\r//'`
    echo "    $line"
    cp "$line" "$auli_cato_loc"
done < "$WHITELIST"