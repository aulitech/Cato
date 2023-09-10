# Code.py for Auli Cato, Driver
# Finn Biggs - finn@auli.tech
# 17-Nov-2022

from utils import config

import microcontroller as mc
from microcontroller import watchdog as w
from watchdog import WatchDogMode
import gc

import asyncio

from imu import LSM6DS3TRC

from StrUUIDService import DebugStream as DBS
import storage

batt_ev = asyncio.Event()
# Beginning code proper


def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

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
        with open("gesture.cato",'r') as cg:
            pass
        with open("gesture.cato",'w') as cg:
            pass
        mc.nvm[2] = True
    except OSError as ose:
        print(ose)
        if(ose.errno == 30):
            print("Rebooting for Gesture Training")
            mc.nvm[0] = False
            mc.reset()
    
    c = Cato( bt = True, do_calib = True )
    Cato.imu.imu_enable.set()

    tasks = {
        "control_loop"  : asyncio.create_task(control_loop( c )),
    }

    tasks.update(c.tasks)
    await asyncio.sleep(0.3)
    Cato.imu.reorient()
    Cato.imu.imu_enable.set()
    Events.control_loop.set()
    try:
        await asyncio.gather(*tasks.values())
    except Exception as ex:
        import traceback
        with open("ErrorLog.txt",'w') as el: 
            el.write(traceback.format_exception(ex))

asyncio.run(main())
