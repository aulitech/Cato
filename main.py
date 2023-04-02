
# Code.py for Auli Cato, Driver
# Finn Biggs - finn@auli.tech
# 17-Nov-2022
import alarm

import board
import sys

import microcontroller as mc
from microcontroller import watchdog as w
from watchdog import WatchDogMode
import supervisor
import gc

import io
import analogio
import digitalio
import busio

import asyncio
import time

from imu import LSM6DS3TRC

import Cato
from Cato import Events
import battery
import mode

from BluetoothControl import DebugStream as DBS

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

async def control_loop(c : Cato.Cato):
    """Control loop for Cato standard operation"""
    while True:
        print("control -- top")
        await Events.control_loop.wait() #await permission to start
        Events.control_loop.clear()

        Events.collect_gestures.set()

        await c.block_on( c._move_mouse )
        Events.detect_event.set()


async def main():
    ##once remount process is confirmed to work consistently, only try/except is necessary
    if(mc.nvm[1]):
        try:
            storage.remount('/', False)
            mc.nvm[1] = False
            DBS.println("Successful remount RO")
        except RuntimeError as re:
            DBS.println("Failed to remount RO")
            print(re)
    else:
        DBS.println("No remount necessary")

    c = Cato.Cato( bt = True, do_calib = True)
    c.imu.imu_enable.set()
    
    tasks = {
        "dog"           : feed_dog(),
        "control_loop"  : control_loop( c ),
    }
    tasks.update(c.tasks)
    await asyncio.sleep(0.3)
    c.imu.imu_enable.set()
    Events.control_loop.set()

asyncio.run(main())
# mode.select_reboot_mode()
