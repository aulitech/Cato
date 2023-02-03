
# Code.py for Auli Cato, Driver
# Finn Biggs - finn@auli.tech
# 17-Nov-2022

import board
import sys

from microcontroller import watchdog as w
from watchdog import WatchDogMode
import supervisor as sp
import gc

import io
import analogio
import digitalio
import busio

import asyncio
import time

import Cato
import battery
import mode

from math import sqrt

batt_ev = asyncio.Event()
# Beginning code proper

w.timeout = 10 #seconds
w.mode = WatchDogMode.RAISE

ti = time.time()
def my_time():
    return time.time() - ti

# async def battery_process():
#     # MOVE TO CATO
#     # read the battery info
#     level = None
#     while True:
#         await batt_ev.wait()
#         batt_ev.clear()
#         c.events.imu_ena.clear()
#         c.imupwr.value = False
#         level = c.battery.level
#         c.blue.battery_service.level = level

#         c.imupwr.value = True
#         c.events.imu_ena.set()

async def feed_dog():
    ''' feed the watchdog '''
    print("feed dog -- top")
    while True:
        w.feed()
        print("dog")
        await asyncio.sleep(8)

def print_boot_out():
    print("boot_out.txt: ")
    with io.open("boot_out.txt") as b: 
        for line in b.readlines():
            print('\t', line, end='')

# State Control / Execution Utils
# MOVE TO MAIN
async def control_loop(c : Cato.Cato):
    """Control loop for Cato standard operation"""
    # await self.events.calibration_done.wait()
    await c.imu.calibrate(100)
    while True:
        print("control -- top")
        await c.events.control_loop.wait() #await permission to start
        c.events.control_loop.clear()

        c.events.collect_gestures.set()

        await c.block_on( c._move_mouse )
        c.events.detect_event.set()

async def main():
    c = Cato.Cato( bt = True, do_calib = True)
    c.imu.imu_enable.set()
    print("")
    tasks = {
        "dog"           : feed_dog(),
        "control_loop"  : control_loop( c ),
    }
    tasks.update(c.tasks)
    print( tasks.keys() )

    c.imu.imu_enable.set()
    await asyncio.sleep(2)
    print(gc.mem_free())
    
    #decide op_mode here?
    c.events.control_loop.set()

    # print([thing for thing in tasks.values()])
    await asyncio.gather( *tasks.values() )

print("Running Main: ")
asyncio.run( main() ) # True -> Debug

# mode.select_reboot_mode()
