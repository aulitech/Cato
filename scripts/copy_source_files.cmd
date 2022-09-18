echo "BEGINNING UPLOAD PROCESS"

if exist E:/ echo "BOARD DETECTED"
else exit
::copy the source files
echo "UPLOADING"
echo "    COPYING .PY FILES"
cp %cd%/*.py /e/
echo "    DONE WITH .PY FILES"
echo "UPLOAD COMPLETE"