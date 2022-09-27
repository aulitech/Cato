import board
import digitalio
import busio
import sys
import json
import time
import microcontroller as mc
import supervisor as sp
from Cato import Cato
from math import sqrt
'''
import os
import gc

fs_stat = os.statvfs('/')
print("Free Ram space: ", gc.mem_free())
print("Disk size in MB", fs_stat[0] * fs_stat[2] / 1024 / 1024)
print("Free space in MB", fs_stat[0] * fs_stat[3] / 1024 / 1024)
'''
mc.nvm[0] = False

cato = Cato()
cato.collect_n_gestures(2)
print("Done with Gestures")
while True:
    try:
        time.sleep(1)
        pass
    except KeyboardInterrupt:
        break

'''
_sum = sum(time_list)
_len = len(time_list)
_sq_list = [i**2 for i in time_list]
_sq_sum = sum(_sq_list)
_mean = _sum / _len
_var = (_sq_sum / _len) - (_mean**2)

print("\nnum: {} \nmean: {} \nstd:{}".format(_len, _mean, sqrt(_var)))
print("")
'''

"""
fs_stat = os.statvfs('/')
print("Free Ram space: ", gc.mem_free())
print("Disk size in MB", fs_stat[0] * fs_stat[2] / 1024 / 1024)
print("Free space in MB", fs_stat[0] * fs_stat[3] / 1024 / 1024)
"""
mc.nvm[0] = True
print("Microcontroller.nvm[0] -> True")

'''
while True:
    Dog.feed()
    if(not cato.blue.ble.connected):
        #code will idle in connectBluetooth until BT is connected
        cato.blue.connect_bluetooth()
    print("Moving")
    cato.move_mouse()
    print("Sleeping")
    sleep_time = 5 
    interval = 1
    for i in range(sleep_time, 0, -interval):
        print("    {}".format(i))
        time.sleep(interval)
'''