import board

import io
import analogio
import digitalio
import busio

import sys
#import json

import time
import mode_selector


import supervisor as sp
import Cato

#from math import sqrt

#import os

print("\n")

#Wait for user to confirm readiness (calibration, readability)
while False:
    try:
        print("Waiting to begin (CtrC)")
        time.sleep(5)
    except KeyboardInterrupt:
            break

# Print battery status
print("\n========= BATTERY =========\n")
battery_pin = analogio.AnalogIn(board.VBATT)
battery_voltage = battery_pin.value / 65536 * 3.3
print("\tV ON BATTERY: {}".format(battery_voltage))
print("\n========= END BATTERY =========\n")

print_boot_out = False
if(print_boot_out == True):
    print("SETUP INFORMATION: ")
    print("boot_out.txt: ")
    with io.open("boot_out.txt") as b: 
        for line in b.readlines():
            print('\t', line, end='')
        b.close()

print("Initializing Cato - interrupt will cause error")
try:
    c = Cato.Cato(bt=True)
    print("Initialization complete.")
except KeyboardInterrupt:
    print("\tinterrupted during initialization")
    pass

try:
    while True:
        x = c.detect_event()
        if not c.blue.ble.connected:
            c.blue.connect_bluetooth()
        #print("I'm right before garbage!")
        #time.sleep(1)
        #print(Cato.garbage)
        c.dispatch_event(x)
except KeyboardInterrupt:
    print("\tinterrupted during gesture detection")

print("\nPROGRAM COMPLETE.\n")

mode_selector.select_reboot_mode()
