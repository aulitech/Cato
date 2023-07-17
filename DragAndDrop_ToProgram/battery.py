import board
import time
import analogio
import digitalio
import asyncio
import json
class Battery:
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
        temp_true = self.b_pin.value
        self.read_bat_ena.value = False # Active Low
        time.sleep(0.1)
        temp_false = self.b_pin.value
        self.read_bat_ena.value = True
        time.sleep(0.1)
        return (temp_true, temp_false)

    @property
    def level(self):
        return 100
