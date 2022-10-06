import board
import io
import digitalio
import busio
import sys
import json
import time
import microcontroller as mc
import supervisor as sp
from Cato import Cato
from math import sqrt
import os

while True:
    try:
        print("Waiting to begin (CtrC)")
        time.sleep(1)
    except KeyboardInterrupt:
            break

print("Continuing to execution")
print("boot_out.txt:")
with io.open("boot_out.txt") as b: 
    for line in b.readlines():
        print(line)
    b.close()

print("Initializing")
try:
    cato = Cato(bt = False)

except KeyboardInterrupt:
    print("interrupted")
    pass

try:
    num_to_detect = 10
    for i in range(num_to_detect):
        cato.detect_event()
except KeyboardInterrupt:
    print("interrupted")

while True:
    try:
        print("done")
        time.sleep(2)
    except KeyboardInterrupt:
        break

boot_timer = 3
def to_computer_writable():
    mc.nvm[0] = True
    print("\nMicrocontroller.nvm[0] -> True")
    print("Rebooting into computer writable mode in {} seconds. For self-writable hit CtrC again".format(boot_timer))
    try:
        for i in range(boot_timer):
            print(boot_timer - i)
            time.sleep(1)
    except KeyboardInterrupt:
        return
    mc.reset()

def to_self_writable():
    mc.nvm[0] = False
    print("\nMicrocontroller.nvm[0] -> False")
    print("Rebooting into self writable mode in {} seconds. For computer-writable hit CtrC again".format(boot_timer))
    try:
        for i in range(boot_timer):
            print(boot_timer - i)
            time.sleep(1)
    except KeyboardInterrupt:
        return
    mc.reset()

self_writable = True
print("Deciding next boot mode: ")
while True:
    
    self_writable =  not self_writable
    if self_writable == True:
        to_self_writable()
    else:
        to_computer_writable()
