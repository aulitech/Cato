import board
import io
import digitalio
import busio
import sys
import json
import time
import microcontroller as mc
import supervisor as sp
import Cato
from math import sqrt
import os

print("\n")

#Wait for user to confirm readiness (calibration, readability)
while False:
    try:
        print("Waiting to begin (CtrC)")
        time.sleep(5)
    except KeyboardInterrupt:
            break

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

boot_timer = 4
def countdown(timer = boot_timer):
    for i in range(timer):
        print(timer - i)
        time.sleep(1)

def to_computer_writable():
    mc.nvm[0] = True
    print("\nMicrocontroller.nvm[0] -> True")
    print("Rebooting into computer writable mode in {} seconds. For self-writable hit CtrC again".format(boot_timer))
    try:
        countdown()
    except KeyboardInterrupt:
        return
    mc.reset()

def to_self_writable():
    mc.nvm[0] = False
    print("\nMicrocontroller.nvm[0] -> False")
    print("Rebooting into self writable mode in {} seconds. For computer-writable hit CtrC again".format(boot_timer))
    try:
        countdown()
    except KeyboardInterrupt:
        return
    mc.reset()

while True:
    print("BOOT MODE / REPL SELECTION")
    print("Type your selection:")
    print("\t0: Computer Writable")
    print("\t1: Self-Writable")
    print("\t2: REPL (or hit Ctr+C)")
    print("INPUT:\t", end='')
    my_str = input()  # type and press ENTER or RETURN
    if my_str=="0":
        to_computer_writable()
    elif my_str == "1":
        to_self_writable()
    elif my_str == "2":
        break
    else:
        print("\tInput not recognized.\n")
