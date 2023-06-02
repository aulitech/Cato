#!/bin/bash

device="Cato"
boot_mount="XIAO-SENSE"
auli_mount="AULI_CATO"
windows_mount="/d/"
WHITELIST="./scripts/whitelist.txt"

await_test () {
   [ $2 "$3" ] && echo -e "$1"

    ct=0
    while [ $2 "$3" ]
    do
        sleep 1
        ct=$((ct+1))
        echo -n "$ct "
        [ $ct -gt $4 ] && echo -e "Failed. $5" && exit 1
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

echo Installing $device Application files on $auli_cato_loc
await_test "Checking for $device." "! -d" "$auli_cato_loc" 30 "Please reset $device with a single tap."

echo "Copying Files:"
while read -r line
do
    line=`echo $line | sed 's/\r//'`
    echo "    $line"
    cp "$line" "$auli_cato_loc"
done < "$WHITELIST"