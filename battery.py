import board
import time
import analogio
import digitalio
import asyncio
import json
class Bat:
    def __init__(self):
        with open('config.json', 'r') as f:
            x = json.load(f)
            self.low = x['battery']['low']
            self.high = x['battery']['high']
        self.b_pin = analogio.AnalogIn(board.VBATT)
        
        self.read_bat_ena = digitalio.DigitalInOut( board.READ_BATT_ENABLE )
        self.read_bat_ena.direction = digitalio.Direction.OUTPUT
        self.read_bat_ena.value = True

        self.charge_st = digitalio.DigitalInOut( board.CHARGE_STATUS )
    
    @property
    def raw_value(self):
        self.read_bat_ena.value = False
        temp = self.b_pin.value
        print(f"Battery: Raw Value = {temp}")
        self.read_bat_ena.value = True
        return temp

    @property
    def level(self):
        value = int( 100 * (self.raw_value - self.low) / (self.high - self.low) )
        if value > 100:
            value = 100
        if value < 0:
            value = 0
        return value
 