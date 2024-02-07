"""
    This file contains utility methods that are not specific to any one class, such as a stopwatch, and translate
    Additionally, this is subsuming mode.py, restart tools will be migrated here.
"""

def unpack_val_dict(d):
    if not isinstance(d, dict):
        return d
    for key in d.keys():
        # print(key)
        d[key] = unpack_val_dict(d[key]["value"])
    return d
    
config = {}
with open("config.json", 'r') as cfg:
    import json
    config = json.load(cfg)

import microcontroller as mc
from binascii import hexlify
uidstr = str(hexlify(mc.cpu.uid))[2:-1]
import os
if(config['global_info']["HW_UID"]["value"] != uidstr)or("0x"+uidstr not in os.listdir()):
    mc.reset()
del(mc)
del(hexlify)
del(os)

unpack_val_dict(config['global_info'])
unpack_val_dict(config['connections'][0])

config.update(config.pop('global_info'))
config.update(config.pop('connections')[0])

# print(config)
import board
import digitalio
pins = {
            "led_green" : digitalio.DigitalInOut( board.LED_GREEN ),
            "led_blue"  : digitalio.DigitalInOut( board.LED_BLUE),
            "led_red"   : digitalio.DigitalInOut( board.LED_RED),
        }
for pin in pins.values():
    pin.direction = digitalio.Direction.OUTPUT
    pin.value = True


import asyncio
import microcontroller as mc
from ulab import numpy as np

def get_mag(arr):
    try:
        return np.linalg.norm(arr)
    except:
        sum = 0.0
        for i in arr:
            sum += i*i
        return np.sqrt(sum)

def comp_writable():
    mc.nvm[0] = True
    mc.reset()

def self_writable():
    mc.nvm[0] = False
    mc.reset()

async def stopwatch(n : float, ev : asyncio.Event = None):
    if(n > 0):
        await asyncio.sleep(n)
        if(ev is not None):
            ev.set()
            # print("Stopwatch, setting event")

def translate(x_min, x_max, y_min, y_max, input):
        
        if input < x_min:
            # print(f"Input ({input}) was less than x_min({x_min})")
            return y_min
        
        if input > x_max:
            # print(f"Input ({input}) was greater than x_max({x_max})")
            return y_max
        
        x_span = x_max - x_min
        y_span = y_max - y_min
        
        scaled = (y_span / x_span) * (input - x_min)
        shifted = scaled + y_min

        return shifted