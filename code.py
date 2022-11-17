import board

import io
import analogio
import digitalio
import busio

import battery

import sys
#import json

import time
import mode

import supervisor as sp
import Cato

import asyncio

#from math import sqrt

#import os

print("\n")

#Wait for user to confirm readiness (calibration, readability)
while False:
    try:
        print("Waiting to begin (CtrC)")
        time.sleep(5)
    except KeyboardInterrupt:
            break


print_boot_out = False
if(print_boot_out == True):
    print("SETUP INFORMATION: ")
    print("boot_out.txt: ")
    with io.open("boot_out.txt") as b: 
        for line in b.readlines():
            print('\t', line, end='')
        b.close()

async def main():
    print("Initializing Cato - interrupt will cause error")
    try:
        c = Cato.Cato( bt=True )
        print("Initialization complete.")
    except KeyboardInterrupt:
        print("\tinterrupted during initialization")
        pass

    while True:
        try:
            await asyncio.sleep(0.1)
            c.blue.battery_service.level = c.battery.get_percent()
            c.move_mouse() #instead of moving mouse as method, have it be blocked on async when not in use
            c.dispatch_event( c.detect_event() ) # dispatch event should always be running
        except:
            break

# async this loop to be await async.sleep(
# bat = battery.Bat()
# ti = time.time()
# try:
#     while True:
#         if(bat.ready):
#             print("bat is ready")
#             print("\tTime is: {}".format(bat.counter.t_now))
#             c.blue.battery_service.level = bat.get_percent()
# except KeyboardInterrupt:
#     print("\tinterrupted during gesture detection")

asyncio.run( main() )

print("\nPROGRAM COMPLETE.\n")

mode.select_reboot_mode()
