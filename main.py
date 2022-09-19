import board
import digitalio
import busio
import sys
import time

from Cato import Cato

class Dog:
    def feed():
        pass

cato = Cato()
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