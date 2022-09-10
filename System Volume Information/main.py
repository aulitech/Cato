import board
import digitalio
import busio
import sys
import time

import Cato as Cato_LIB

cato = Cato_LIB.Cato()
num_to_move = 5000
while True:
    print("moving")
    cato.read_IMU()
    cato.move_Mouse()
    print("sleeping")
    for i in range(3,0,-1):
        time.sleep(1)
        print(i)