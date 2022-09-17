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
    cato.scroll()
    print("Sleeping")
    for i in range(5, 0, -1):
        print(i)
        time.sleep(1)