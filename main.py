
# Code.py for Auli Cato, Driver
# Finn Biggs - finn@auli.tech
# 17-Nov-2022
'''
import alarm

import board
import sys
'''
import microcontroller as mc
from microcontroller import watchdog as w
from watchdog import WatchDogMode
#import supervisor as sp
import gc

'''
import io
import analogio
import digitalio
import busio
'''

import asyncio
#import time

from imu import LSM6DS3TRC

from Cato import Cato, Events
#import battery
#import mode

from StrUUIDService import DebugStream as DBS
import storage

batt_ev = asyncio.Event()
# Beginning code proper


def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

async def feed_dog():
    ''' feed the watchdog '''
    w.timeout = 10 #seconds
    w.mode = WatchDogMode.RAISE
    while True:
        w.feed()
        await asyncio.sleep(8)

async def control_loop(c : Cato):
    """Control loop for Cato standard operation (MODE 0)"""
    while True:
        print("@ control_loop")
        await Events.control_loop.wait() #await permission to start
        Events.control_loop.clear()

        await c.block_on( c._move_mouse )
        Events.mouse_event.set()

async def main():
    try:
        with open("cg.txt",'r') as cg:
            print("File Found!!!")
        with open("cg.txt",'w') as cg:
            print("Booted Self-Writable")
        print("Deleting File")
        mc.nvm[2] = True
    except OSError as ose:
        print(ose)
        if(ose.errno == 2):
            print("File Not Found :(")
        elif(ose.errno == 30):
            print("Needs Reboot")
            mc.nvm[0] = False
            mc.reset()
    
    
    ##once remount process is confirmed to work consistently, only try/except is necessary
    if(mc.nvm[1]):
        try:
            storage.remount('/', False)
            mc.nvm[1] = False
            DBS.println("Successful remount RO")
        except RuntimeError as re:
            DBS.println("COM port detected")
    else:
        DBS.println("No remount necessary")
    # print(f"+ main/main {gc.mem_free()}")
    c = Cato( bt = True, do_calib = True)
    # print(f"+ main/cato_created {gc.mem_free()}")
    Cato.imu.imu_enable.set()
    # print(f"+ main/imu_ena set {gc.mem_free()}")

    tasks = {
        # "dog"           : asyncio.create_task(feed_dog()),
        "control_loop"  : asyncio.create_task(control_loop( c )),
    }
    tasks.update(c.tasks)
    await asyncio.sleep(0.3)
    Cato.imu.imu_enable.set()
    Events.control_loop.set()
    await asyncio.gather(*tasks.values())


asyncio.run(main())
