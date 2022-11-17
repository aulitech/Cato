import board

import io
import analogio
import digitalio
import busio
import asyncio

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

# print("\n")

# #Wait for user to confirm readiness (calibration, readability)
# while False:
#     try:
#         print("Waiting to begin (CtrC)")
#         time.sleep(5)
#     except KeyboardInterrupt:
#             break

async def battery_process():
    # read the battery info
    # STUB
    asyncio.sleep(30)

async def feed_dog():
    ''' feed the watchdog '''
    asyncio.sleep(20)

async def loop():
    ''' docstring '''
    while True:
        asyncio.sleep(2)

def print_boot_out():
    print("boot_out.txt: ")
    with io.open("boot_out.txt") as b: 
        for line in b.readlines():
            print('\t', line, end='')

async def main():
    # print_boot_out()
    c = Cato( bt = True )

    tasks = []
    tasks.append( asyncio.create_task( battery_process() ) )
    tasks.append( asyncio.create_task( loop() ) )
    tasks.append( asyncio.create_task( feed_dog() ) )
    await asyncio.gather( *tasks )

# async def main():
#     print("Initializing Cato - interrupt will cause error")
#     try:
#         c = Cato.Cato( bt=True )
#         print("Initialization complete.")
#     except KeyboardInterrupt:
#         print("\tinterrupted during initialization")
#         pass

#     while True:
#         try:
#             await asyncio.sleep(0.1)
#             c.blue.battery_service.level = c.battery.get_percent()
#             c.move_mouse() #instead of moving mouse as method, have it be blocked on async when not in use
#             c.dispatch_event( c.detect_event() ) # dispatch event should always be running
#         except:
#             break

# asyncio.run( main() )

# print("\nPROGRAM COMPLETE.\n")

# mode.select_reboot_mode()
