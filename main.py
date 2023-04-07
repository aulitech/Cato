
# Code.py for Auli Cato, Driver
# Finn Biggs - finn@auli.tech
# 17-Nov-2022
import alarm

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

from imu import LSM6DS3TRC

import Cato
import battery
import mode

from math import sqrt

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
    c = Cato.Cato()
    if( c.config['operation_mode'] == 'pointer'):
        Cato.Events.move_mouse.set()
    if( c.config['operation_mode'] == 'clicker'):
        c.imu.single_tap_cfg()
        c.tasks.update({"click" : asyncio.create_task(c.click())})
    await asyncio.gather(*c.tasks.values())

asyncio.run(main())
# mode.select_reboot_mode()
