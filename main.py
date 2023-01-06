
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

# Beginning code proper
c = Cato.Cato( bt = True, do_calib = False )
w.timeout = 10 #seconds
w.mode = WatchDogMode.RAISE

ti = time.time()
def my_time():
    return time.time() - ti

async def battery_process():
    # read the battery info
    local_c = c
    level = None
    while True:
        level = local_c.battery.level
        local_c.blue.battery_service.level = level
        await asyncio.sleep(30)

async def feed_dog():
    ''' feed the watchdog '''
    while True:
        w.feed()
        await asyncio.sleep(3)

def print_boot_out():
    print("boot_out.txt: ")
    with io.open("boot_out.txt") as b: 
        for line in b.readlines():
            print('\t', line, end='')

async def main():
    # print_boot_out()
    tasks = []
    tasks.append( asyncio.create_task( battery_process() ) )
    tasks.append( asyncio.create_task( feed_dog() ) )
    for t in c.tasks:
         tasks.append(t)
    print("MAIN: setting default_move_mouse")
    c.events.default_move_mouse.set() 
    await asyncio.gather( *tasks )

asyncio.run( main() ) # True -> Debug

# mode.select_reboot_mode()
