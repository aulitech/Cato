
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

async def control_loop(c : Cato.Cato):
    """Control loop for Cato standard operation"""
    while True:
        await Cato.Events.control_loop.wait() #await permission to start
        Cato.Events.control_loop.clear()
        # print("A")
        await c.block_on( c._move_mouse )
        # print("B")
        Cato.Events.detect_event.set()

async def blink():
    RGB = {
        "R" : digitalio.DigitalInOut( board.LED_RED ),
        "G" : digitalio.DigitalInOut( board.LED_GREEN ),
        "B" : digitalio.DigitalInOut( board.LED_BLUE )
    }
    for led in RGB.values():
        led.direction = digitalio.Direction.OUTPUT
        led.value = True
    while True:
        for led in RGB.values():
            led.value = False
            await asyncio.sleep(0.5)
            led.value = True
            await asyncio.sleep(0.5)

# async def light_sleep_task():
#     while True:
#         await asyncio.sleep(10)
#         time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + 10)
#         alarm.light_sleep_until_alarms(time_alarm)

async def deep_sleep_task():
    await asyncio.sleep(5)
    pin_alarm = alarm.pin.PinAlarm(pin = board.IMU_INT1, value = True)
    alarm.exit_and_deep_sleep_until_alarms(pin_alarm)

async def pin_sleep_task():
    while True:
        await asyncio.sleep(3)
        pin_alarm = alarm.pin.PinAlarm(pin=board.IMU_INT1, value = True)
        print("going to sleep")
        alarm.light_sleep_until_alarms(pin_alarm)
        print("woke from sleep")

async def main():
    c = Cato.Cato()
    tasks = {
        "control_loop"  : control_loop(c),
        "dog"           : feed_dog(),
    }
    tasks.update(c.tasks)
    Cato.Events.control_loop.set()
    print(tasks.keys())
    await asyncio.gather( *tasks.values() )

print("Running Main: ")
asyncio.run( main() ) # True -> Debug

# mode.select_reboot_mode()
