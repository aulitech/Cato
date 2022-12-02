import board
import time
import analogio
import asyncio

class Bat:

    #These separate for data collection stuff on battery life
    # default_file = "BatteryData.csv"
    # need_to_clear_default_file = True
    # has_set_time = False
    # ti = time.time()
    # i = 1
    
    #where the generally applicable stuff goes
    def __init__(self):
        self.b_pin = analogio.AnalogIn(board.VBATT)

    @property
    def raw_value(self):
        return self.b_pin.value

    @property
    def level(self):
        val_floor = 62305 # lowest recorded value in battery trial
        val_ceil = 65535  # highest value on analog pin
        
        frac = (self.raw_value -  val_floor) / ( val_ceil - val_floor) # fraction for location between lowest and higest
        #convert to percentage rounding to nearest int (e.g. 100*frac = 99.63 --add 0.5--> 100.53 --truncate--> 100%)
        return int( (100 * frac) + 0.5 ) 
