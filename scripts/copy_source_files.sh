#!/bin/bash
echo "Checking connection"
while [ ! -d /e/ ]
do
    sleep 1
    echo "    Waiting for connection"
done

echo "    CONNECTED"
# copy the source files
    echo "UPLOADING"
    echo "    COPYING .PY FILES"
    cp ./*.py /e/
    echo "    DONE WITH .PY FILES"
    echo "UPLOAD COMPLETE"