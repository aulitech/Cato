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
    if(not cato.Blue.ble.connected):
        #code will idle in connectBluetooth until BT is connected
        cato.Blue.connectBluetooth()
    print("moving")
    cato.moveMouse()
    print("sleeping")
    for i in range(3,0,-1):
        time.sleep(1)
        print(i)