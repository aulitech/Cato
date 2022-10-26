
import time

class Counter():
    
    def __init__(self, dt = 1):
        self.n = 0
        self.dt = dt
        self.ti = time.monotonic()

    @property
    def t_next(self):    
        return self.n * self.dt

    @property
    def t_now(self):
        return time.monotonic() - self.ti

    @property
    def ready(self):

        # time_gap: how long until the next "ready." If this is too big, we shift n until it's within one dt
        time_gap = self.t_next - self.t_now
        while (time_gap > self.dt):
            self.n += 1
            time_gap = self.t_next - self.t_now

        if(self.t_now >= self.t_next):
            self.n += 1
            #print("Ding at {}".format(time.monotonic()))
            return True 
        return False


