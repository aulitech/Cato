import board
import time
import analogio
import digitalio
import asyncio
import json
class Bat:
    def __init__(self):
        with open('battery_levels.json', 'r') as f:
            x = json.load(f)
            self.low = x['low']
            self.high = x['high']
        self.b_pin = analogio.AnalogIn(board.VBATT)
        
        self.read_bat_ena = digitalio.DigitalInOut( board.READ_BATT_ENABLE )
        self.read_bat_ena.direction = digitalio.Direction.OUTPUT
        self.read_bat_ena.value = True

        self.charge_st = digitalio.DigitalInOut( board.CHARGE_STATUS )
    
    @property
    def raw_value(self):
        self.read_bat_ena.value = False
        time.sleep(0.12)
        temp = self.b_pin.value
        self.read_bat_ena.value = True
        print(f"Battery: Raw Value = {temp}")
        return temp

    @property
    def level(self):
        value = int( 100 * (self.raw_value - self.low) / (self.high - self.low) )
        if value > 100:
            value = 100
        if value < 0:
            value = 0
        return value
 