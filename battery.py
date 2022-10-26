import board
import time
import analogio
from Counter import Counter

class Bat:

    #These separate for data collection stuff on battery life
    # default_file = "BatteryData.csv"
    # need_to_clear_default_file = True
    # has_set_time = False
    # ti = time.time()
    # i = 1
    
    #where the generally applicable stuff goes
    def __init__(self):
        self.dt = 30
        self.counter = Counter(self.dt)
        self.b_pin = analogio.AnalogIn(board.VBATT)

    @property
    def value(self):
        return self.b_pin.value

    @property 
    def ready(self):
        return self.counter.ready

    def get_percent(self):
        val_floor = 62305 # lowest recorded value in battery trial
        val_ceil = 65535  # highest value on analog pin
        
        frac = (self.value -  val_floor) / ( val_ceil - val_floor) # fraction for location between lowest and higest
        #convert to percentage rounding to nearest int (e.g. 100*frac = 99.63 --add 0.5--> 100.53 --truncate--> 100%)
        return int( (100 * frac) + 0.5 ) 

    # def write_value_to_file(self, file =  default_file):
        
    #     if self.need_to_clear_default_file:
    #         with open(file, "w") as f:
    #             f.write("")
    #         self.need_to_clear_default_file = False
            
    #     with open( file, "a" ) as f:
    #         print("{}, {}".format(time.time() - self.ti, self.value))
    #         f.write( "{}, {}\n".format(time.time() - self.ti, self.value) )

    # def manage_collection(self):
    #     if not self.has_set_time:
    #         self.has_set_time = True
    #         self.ti = time.time()
    #     if ( (time.time() - self.ti) >= (self.i * self.dt) ):
    #         self.write_value_to_file()
    #         self.i += 1