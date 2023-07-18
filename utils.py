"""
    This file contains utility methods that are not specific to any one class, such as a stopwatch, and translate
    Additionally, this is subsuming mode.py, restart tools will be migrated here.
"""

def unpack_val_dict(d):
    if not isinstance(d, dict):
        return d
    for key in d.keys():
        d[key] = unpack_val_dict(d[key]["value"])
    return d
    
config = {}
with open("config.json", "r") as f:
    import json
    config = unpack_val_dict(json.load(f))
    

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
        sum = np.sqrt(sum)
        return sum

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
            return y_min
        if input > x_max:
            return y_max
        
        x_span = x_max - x_min
        y_span = y_max - y_min
        
        scaled = (y_span / x_span) * (input - x_min)
        shifted = scaled + y_min
        return shifted