import board
import time
import analogio
import digitalio
import asyncio
from StrUUIDService import DebugStream as DBS
from utils import config, translate
class Battery:
    def __init__(self):
        self.b_pin = analogio.AnalogIn(board.VBATT)
        self.read_bat_ena = digitalio.DigitalInOut( board.READ_BATT_ENABLE )
        self.read_bat_ena.direction = digitalio.Direction.OUTPUT
        self.read_bat_ena.value = True

        self.charge_st = digitalio.DigitalInOut( board.CHARGE_STATUS )
        
    @property
    def raw_value(self):

        self.read_bat_ena.value = False # Active Low
        time.sleep(0.05)

        temp = self.b_pin.value

        self.read_bat_ena.value = True
        time.sleep(0.05)

        # DBS.println(f"Battery analog level: {temp}")
        return temp 

    @property
    def level(self):
        level = translate(config["battery"]["low"], config["battery"]["high"], 0, 100, self.raw_value)
        DBS.println(f"level = {self.raw_value}")
        return int(level)
