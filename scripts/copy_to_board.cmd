
@echo off

:hang_bootloader_check_head
if exist E:/boot_out.txt echo BOARD MUST BE IN BOOTLOADER MODE. TAP RESET 2x

:hang_bootloader_check
if exist E:/boot_out.txt echo     WAITING. TAP RESET 2x
:: PING IS A DELAY COMMAND
ping 192.0.2.2 -n 1 -w 1000 > nul
if exist E:/boot_out.txt goto hang_bootloader_check

::must wait for board to reconnect after double tap 
echo WAITING FOR RECONNECT AFTER POWER CYCLE
:hang_reconnect_empty
echo     WAITING FOR AUTOMATIC BOARD RECONNECT
ping 192.0.0.2 -n 1 -w 1000 > nul
if not exist E:/ goto hang_reconnect_empty
echo CONNECTION ESTABLISHED

::ensure board is properly in bootloader mode
echo CHECKING CONFIG
set "config_ok=F"
if exist E:/INFO_UF2.TXT if exist E:/INDEX.HTM if exist E:/CURRENT.UF2 set "config_ok=T"
if %config_ok%==T echo     VALIDATED
if %config_ok%==F echo     NOT VALID
if %config_ok%==F goto hang_bootloader_check_head

::copy new uf2
echo COPYING BOOTLOADER TO E:/ ~5 seconds
cp %cd%/.bootloader/* /e/
echo     COPIED

echo BOARD WILL RESTART AND RECONNECT
:hang_reconnect_as_circuitpy
echo     WAITING FOR AUTO-RECONNECT
ping 192.0.2.2 -n 1 -w 1000 > nul
if not exist E:/boot_out.txt goto :hang_reconnect_as_circuitpy
echo     CONNECTION ESTABLISHED

::copy source files
echo COPYING *.PY FILES TO BOARD
cp %cd%/*.py /e/
echo     PY FILES COPIED
echo COPYING /lib/ (TAKES TIME)
cp -r %cd%/lib/ /e/
echo     LIBS COPIED
echo     DONE
exit