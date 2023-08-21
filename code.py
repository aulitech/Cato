# code for checking battery connection in flex casing

import board
import digitalio
import time

ledR = digitalio.DigitalInOut(board.LED_RED)
ledB = digitalio.DigitalInOut(board.LED_BLUE)
ledG = digitalio.DigitalInOut(board.LED_GREEN)

ledR.direction = ledB.direction = ledG.direction = digitalio.Direction.OUTPUT
ledR.value = ledB.value = ledG.value = True

for i in range(5):
    ledR.value = False
    time.sleep(0.1)
    ledR.value = True
    time.sleep(0.1)


while True:
    ledB.value = True
    ledG.value = False
    time.sleep(0.5)
    ledB.value = False
    ledG.value = True
    time.sleep(0.5)