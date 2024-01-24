#!/bin/zsh
#
# This works around bug where, by default, macOS writes part of a file
# immediately, and then doesn't update the directory for 20-60 seconds, causing
# the file system to be corrupted.
#

# Find the USB Drive to be updated, not found? exit
disky=`df | grep AULI_CATO | cut -d" " -f1`
#echo "Found Cato at $disky"
[[ -z $disky ]] && echo "Can't find Cato" && exit 1
[[ ! -d drag_and_drop ]] && echo "This script must be run from the Release directory" && exit 1


echo "Admin password required to update Cato"
sudo umount /Volumes/AULI_CATO
sudo mkdir /Volumes/AULI_CATO
sleep 2
sudo mount -v -o noasync -t msdos $disky /Volumes/AULI_CATO > /dev/null
sleep 2

echo "Updating Cato"
rm -rf /Volumes/AULI_CATO/*
cp -r drag_and_drop/* /Volumes/AULI_CATO
echo "Cato updated"