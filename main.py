
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
 
import asyncio

from imu import LSM6DS3TRC

from Cato import Cato

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


async def main():
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

    c = Cato( bt = True, do_calib = True)
    print("Cato created")
    Cato.imu.imu_enable.set()
    print("imu_enable set")
    tasks = {
        "dog"           : asyncio.create_task(feed_dog())
    }
    print("dog task created")
    tasks.update(c.tasks)
    await asyncio.sleep(1)
    print("update tasks w Cato tasks")
    Cato.imu.imu_enable.set()
    print("gathering in main")
    await asyncio.gather(*tasks.values())


asyncio.run(main())
# mode.select_reboot_mode()
#Here is a new comment