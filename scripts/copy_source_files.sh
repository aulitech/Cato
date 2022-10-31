#!/bin/bash

auli_cato_loc=/e/
echo "Checking connection"
while [ ! -d $auli_cato_loc ]
do
    sleep 1
    echo "    Waiting for connection"
done

echo "    CONNECTED"
# copy the source files
    echo "UPLOADING"
    echo "    COPYING .PY FILES"
    cp ./*.py $auli_cato_loc
    echo "    DONE WITH .PY FILES"
    echo "UPLOAD COMPLETE"