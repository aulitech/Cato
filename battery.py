import board
import time
import analogio
import digitalio
import asyncio

class Bat:
    def __init__(self):
        self.b_pin = analogio.AnalogIn(board.VBATT)
        
        self.read_bat_ena = digitalio.DigitalInOut( board.READ_BATT_ENABLE )
        self.read_bat_ena.direction = digitalio.Direction.OUTPUT
        self.read_bat_ena.value = True

        self.charge_st = digitalio.DigitalInOut( board.CHARGE_STATUS )
    
    @property
    def raw_value(self):
        self.read_bat_ena.value = False
        time.sleep(0.1)
        temp = self.b_pin.value
        self.read_bat_ena.value = True
        return temp

    @property
    def level(self):
        low = 0
        high = 65535
        value = int( 100 * (self.raw_value - low) / (high - low) )
        # print(f"Raw value reads as: {self.raw_value}")
        # print(f"Scaled value reads as: {value}")
        return value
 