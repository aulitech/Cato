'''
Cato.py
auli.tech software to drive the Cato gesture Mouse
Written by Finn Biggs finn@auli.tech
    15-Sept-22
'''
import sys
import board
import microcontroller as mc

import busio
import os
import io
import json
import time
import digitalio
import countio

from imu import LSM6DS3TRC

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from math import sqrt, atan2, sin, cos, pow, pi
import array
import supervisor as sp
import battery

import asyncio

import gc

from neutonml import Neuton

#helpers and enums

class ST():
    '''enum states'''
    IDLE = 0
    MOUSE_BUTTONS = 1
    KEYBOARD = 2


class EV(): #these are actually gestures
    ''' enum events '''
    UP = 0
    DOWN = 1
    RIGHT = 2
    LEFT = 3
    ROLL_R = 4
    ROLL_L = 5
    SHAKE_YES = 6
    SHAKE_NO = 7
    NONE = 8

class Events:
    def __init__(self):
        self.imu_setup              = asyncio.Event()   # indicates the imu has been config'd
        self.imu                    = asyncio.Event()   # indicates new data is available from the imu
        self.data_ready             = asyncio.Event()   # indicates that gyro and sensor are ready to read from gx_hist, gy_hist, gz_hist
        self.calibration_done       = asyncio.Event()   # indicates that calibration has been completed, blocks default_move_mouse
        self.default_move_mouse     = asyncio.Event()   # standard move mouse, but sets detect event after
        self.move_mouse             = asyncio.Event()   # move the mouse
        self.mouse_done             = asyncio.Event()   # indicates mouse movement has finished
        self.scroll                 = asyncio.Event()   # scroll the screen
        self.scroll_done            = asyncio.Event()   # indicates scroll has finished
        self.scroll_lr              = asyncio.Event()   # scroll left to right
        self.scroll_lr_done         = asyncio.Event()   # indicates that scroll_lr has completed
        self.wait_for_motion        = asyncio.Event()   # wait_for_motion
        self.wait_for_motion_done   = asyncio.Event()   # wait-for-motion exit indicator
        self.sig_motion             = asyncio.Event()   # indicates that there has been significant motion during wait_for_motion's window
        self.stream_imu             = asyncio.Event()   # stream data from the imu onto console -- useful for debugging
        self.detect_event           = asyncio.Event()   # triggers detection of Cato gesture
        self.idle                   = asyncio.Event()   # triggered when no events change for some time
        self.collect_garbage        = asyncio.Event()   # triggers collection of garbage
        self.collect_garbage_done   = asyncio.Event()   # indicates garbage collection finished

    def print_status(self):
        pass


neuton_outputs = array.array( "f", [0, 0, 0, 0, 0, 0, 0, 0] )

def mem():
    print(f"MEM FREE: {gc.mem_free()}")

class Cato:
    ''' Main Class of Cato Gesture Mouse '''
    def __init__(self, bt:bool = True, do_calib = True):
        mem()
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        try:    
            with open("config.json", 'r') as f:
                self.config = json.load(f)
        except:
            mc.reset()


        #specification for operation
        self.specs = {
            "freq" : 104.0, # imu measurement frequency (hz)
            "g_dur": 0.75   # gesture duration (s)
        }

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish

        # number of samples in one neuton gesture
        self.specs["num_samples"] = int(self.specs["freq"] * self.specs["g_dur"])

        # battery managing container
        self.battery = battery.Bat()


        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        self.blue = BluetoothControl.BluetoothControl()
        
        self.state = ST.IDLE
        self.st_matrix = [ # TODO: Read this from CONFIG.JSON
                #   ST.IDLE                     ST.MOUSE_BUTTONS            ST.KEYBOARD
                [   self._move_mouse,           self.to_idle,               self.to_idle        ], # EV.UP           = 0
                [   self.left_click,            self.left_click,            self.press_enter    ], # EV.DOWN         = 1
                [   self._scroll,               self.noop,                  self.noop           ], # EV.RIGHT        = 2
                [   self._wait_for_motion,      self.noop,                  self.noop           ], # EV.LEFT         = 3
                [   self._scroll_lr,             self.noop,                  self.noop           ], # EV.ROLL_R       = 4
                [   self._scroll_lr,             self.noop,                  self.noop           ], # EV.ROLL_L       = 5
                [   self.double_click,          self.noop,                  self.noop           ], # EV.SHAKE_YES    = 6
                [   self._wait_for_motion,       self.noop,                  self.noop           ], # EV.SHAKE_NO     = 7
                [   self.noop,                  self.noop,                  self.noop           ]  # EV.NONE         = 8
        ]
        # initial buffer position
        self.buf = 0

        self.gx_hist    = [0] * (self.specs["num_samples"])
        self.gy_hist    = [0] * (self.specs["num_samples"])
        self.gz_hist    = [0] * (self.specs["num_samples"])
        self.ax_hist    = [0] * (self.specs["num_samples"])
        self.ay_hist    = [0] * (self.specs["num_samples"])
        self.az_hist    = [0] * (self.specs["num_samples"])
        self.time_hist  = [0] * (self.specs["num_samples"])


        self.gx_trim, self.gy_trim, self.gz_trim = 0, 0, 0

        self.events = Events()

        # blocking functions enabled by events
        self.tasks = [
            asyncio.create_task( self.wait_for_motion() ),
            asyncio.create_task( self.default_move_mouse() ),
            asyncio.create_task( self.move_mouse() ),
            asyncio.create_task( self.read_imu() ),
            asyncio.create_task( self.int_imu() ),
            asyncio.create_task( self.detect_event() ),
            asyncio.create_task( self.scroll() ),
            asyncio.create_task( self.scroll_lr() ),
            asyncio.create_task( self.collect_garbage() )
        ]

        self.sensor = self.setup_imu()
        if do_calib:
            self.tasks.append( asyncio.create_task( self.calibrate() ) )
        else:
            self.events.calibration_done.set()

        self.n = Neuton(outputs=neuton_outputs)
        
        for t in self.blue.tasks:
            self.tasks.append(t)
        
        self.gesture = EV.NONE
        print(self.events)

        mem()

    def setup_imu(self):
        ''' helper method -- encapsulate imu portioof init '''
        print("IMU setup ...")

        # enable imu
        imupwr = digitalio.DigitalInOut(board.IMU_PWR)
        imupwr.direction = digitalio.Direction.OUTPUT
        imupwr.value = True

        time.sleep(0.1) # required delay on imu

        imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        sensor = LSM6DS3TRC(imu_i2c)
        
        # config info at:
        # https://cdn.sparkfun.com/assets/learn_tutorials/4/1/6/AN4650_DM00157511.pdf
        # here, we set the GDA bit of the INT1_CTRL register to True, 
        #   to push Data Ready (gyro) signal to INT1 pin for interrupt
        sensor.int1_ctrl = 0x02

        self.events.imu_setup.set()
        print("    Done")
        return sensor
    
    async def read_imu(self):
        ''' reads data off of the IMU into -> gx, gy, gz, ax, ay, az '''
        #just once start the spin?
        await self.events.imu_setup.wait() # don't read until imu is set up
        
        self.sensor.gyro # clears data
        
        while True:
            # hold until data ready
            # print("awaiting imu")
            await self.events.imu.wait()
            self.events.imu.clear()

            #iterate and record
            self.buf = (self.buf + 1) % self.specs["num_samples"]
            self.time_hist[self.buf] = sp.ticks_ms()

            # read from IMU
            self.gx_hist[self.buf], self.gy_hist[self.buf], self.gz_hist[self.buf] = self.sensor.gyro
            self.ax_hist[self.buf], self.ay_hist[self.buf], self.az_hist[self.buf] = self.sensor.acceleration
            
            # conv to degrees
            rad_to_deg = 360.0 / (2 * pi)
            self.gx_hist[self.buf] *= rad_to_deg
            self.gy_hist[self.buf] *= rad_to_deg
            self.gz_hist[self.buf] *= rad_to_deg

            # trim measurements based on calibration
            self.gx_hist[self.buf] -= self.gx_trim
            self.gy_hist[self.buf] -= self.gy_trim
            self.gz_hist[self.buf] -= self.gz_trim
            
            self.events.data_ready.set()

            # print("- end of read_imu -")


    async def int_imu(self):
        """ interrupt on imu for gyro data ready """
        with countio.Counter(   
            board.IMU_INT1, 
            edge = countio.Edge.RISE, 
            pull = digitalio.Pull.DOWN 
        ) as interrupt:
            while True:
                if interrupt.count > 0:
                    interrupt.count = 0
                    # print("interrupted!")
                    self.events.imu.set()
                await asyncio.sleep(0)

    async def calibrate(self, num = 50):
        """ method to determine hardware drift of imu """ 
        _f = self.specs["freq"]
        print(f"CALIBRATE: ESTIMATE 2 SECONDS")
        x, y, z = 0, 0, 0
        for cycles in range(num):
            await self.events.data_ready.wait()
            self.events.data_ready.clear()

            x += self.gx
            y += self.gy
            z += self.gz
        self.gx_trim = x / num
        self.gy_trim = y / num
        self.gz_trim = z / num
        print("CALIBRATION: COMPLTED")
        self.events.calibration_done.set()
        
    async def stream_imu(self):
        while True:
            await self.events.data_ready.wait()
            print(f"{self.time_hist[self.buf]}: {self.gx}, {self.gy}, {self.gz}")
            self.events.data_ready.clear()
    
    def display_gesture_menu(self):
        print("Available actions: ")
        for ev in range(len(self.st_matrix)):
            print("\tevent: {}\n\t\taction: {}".format(ev, self.st_matrix[ev][self.state].__name__))

    def _detect_event(self):
        self.events.detect_event.set()

    async def _move_mouse(self, hall_pass: asyncio.Event = None):
        print('_move_mouse: move_mouse set')
        self.events.move_mouse.set()

        print("_move_mouse: awaiting mouse_done")
        await self.events.mouse_done.wait()
        self.events.mouse_done.clear()

        print("_move_mouse: recieved mouse_done")
        print("_move_mouse: hall_pass set")
        if hall_pass is not None:
            hall_pass.set()

    # State Control / Execution Utils

    async def default_move_mouse(self):
        ''' 
            controls basic flow into and out of mouse move
            should maybe be renamed
        '''
        print('DMM: awaiting calibration confirm')
        await self.events.calibration_done.wait()
        print("DMM: recieved calibration complete signal")

        while True:
            
            print("DMM: awaiting default_move_mouse")
            await self.events.default_move_mouse.wait() #await permission to start
            self.events.default_move_mouse.clear()
            print("DMM: recieved & cleared default_move_mouse")
            
            print("DMM: mouse set, waiting for finish")
            self.events.move_mouse.set()
            await self.events.mouse_done.wait()
            self.events.mouse_done.clear()
            print("DMM: mouse finished and flag cleared")

            print('DMM: ATTEMPTING TO COLLCET GARBAGE')
            await self._collect_garbage()
            print("DMM: GARBAGE COLLECTED")

            print("DMM: detect_event set")
            self.events.detect_event.set()
    
    async def _collect_garbage(self):
        mem()
        print("_collect_garbage: setting")
        self.events.collect_garbage.set()
        print("_collect_garbage: awaiting done signal")
        await self.events.collect_garbage_done.wait()
        self.events.collect_garbage_done.clear()
        print("_collect_garbage: done signal cleared, exiting")
        mem()

    async def detect_event(self):
        ''' calls to gesture detection libraries '''
        while True:
            gesture = EV.NONE
            print("D_EV: awaiting detect_event")
            await self.events.detect_event.wait()
            self.events.detect_event.clear()
            print("D_EV: recieved & cleared detect_event")
            print("D_EV: wait_for_motion")

            await self.shake_cursor()

            self.events.wait_for_motion.set()
            await self.events.wait_for_motion_done.wait()
            self.events.wait_for_motion_done.clear()
            print("D_EV: recieved & cleared wait_for_motion_done")

            motion_detected = self.events.sig_motion.is_set()
            
            if motion_detected:
                print("D_EV: wait_for_motion found motion")
                self.events.sig_motion.clear()
                #read_imu enough times
                for i in range(self.specs['freq']):
                    await self.events.data_ready.wait()
                    self.events.data_ready.clear()

                neuton_needs_more_data = True
                arr = array.array( 'f', [0]*6)
                
                i = 1 #buf pos tracker
                while(True):
                    b_pos = (i + self.buf) % self.specs["num_samples"]
                    arr[0] = self.ax_hist[b_pos]
                    arr[1] = self.ay_hist[b_pos]
                    arr[2] = self.az_hist[b_pos]
                    arr[3] = self.gx_hist[b_pos]
                    arr[4] = self.gy_hist[b_pos]
                    arr[5] = self.gz_hist[b_pos]
                    neuton_needs_more_data = self.n.set_inputs( arr )
                    i += 1
                    # runs until neuton doesn't need more data
                    if bool(neuton_needs_more_data) == False:
                        break

                gesture = self.n.inference()
                confidence = max(neuton_outputs)

                confidence_thresh = 0.80
                if confidence < confidence_thresh:
                    gesture = EV.NONE

            else:
                print("D_EV: wait_for_motion timed out")
                gesture = EV.NONE
            
            print('D_EV: ATTEMPTING TO COLLCET GARBAGE')
            await self._collect_garbage()
            print("D_EV: GARBAGE COLLECTED")
            
            mem()
            target_fn = self.st_matrix[gesture][self.state]
            print(f"target_fn: {target_fn.__name__}")

            await target_fn( self.hall_pass )
            
            mem()

            print(f"D_EV: awaiting hall_pass to be set by target function")
            await self.hall_pass.wait()
            self.hall_pass.clear()

            
            print("D_EV: hall_pass recieved & cleared")

            await self._collect_garbage()
            
            print("D_EV: default_move_mouse set")
            self.events.default_move_mouse.set()


    # Sensor utils read_IMU, calibrate
    @property
    def gx(self):
        return self.gx_hist[self.buf]
    
    @property
    def gy(self):
        return self.gy_hist[self.buf]
    
    @property
    def gz(self):
        return self.gz_hist[self.buf]

    @property
    def ax(self):
        return self.ax_hist[self.buf]

    @property
    def ay(self):
        return self.ay_hist[self.buf]

    @property
    def az(self):
        return self.az_hist[self.buf]

    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    async def noop(self, hall_pass: asyncio.Event = None):
        ''' no operation '''
        print("nooping")
        if hall_pass is not None:
            hall_pass.set()
    
    async def to_idle(self, hall_pass: asyncio.Event = None):
        self.state = ST.IDLE
        if hall_pass is not None:
            hall_pass.set()
    
    async def to_mouse_buttons(self, hall_pass: asyncio.Event = None):
        self.state = ST.MOUSE_BUTTONS
        if hall_pass is not None:
            hall_pass.set()
    
    async def to_keyboard(self, hall_pass: asyncio.Event = None):
        self.state = ST.KEYBOARD
        if hall_pass is not None:
            hall_pass.set()
        
    # Cato Mouse Actions
    async def shake_cursor(self, hall_pass: asyncio.Event = None):
        m = self.blue.mouse
        mv_size = 10
        num_wiggles = 2
        moves = [
            (-mv_size,      0,          0),
            (0,             mv_size,    0),
            (2*mv_size,     0,          0),
            (0,             -2*mv_size, 0),
            (-2*mv_size,    0,          0),
            (0,             2*mv_size,  0),
            (mv_size,       -mv_size,   0)
        ]

        for wiggle in range(num_wiggles):
            for move in moves:
                await asyncio.sleep(0.03)
                self.blue.mouse.move(*move)

    def translate(x_min, x_max, y_min, y_max, input):
        if input < x_min:
            return y_min
        if input > x_max:
            return y_max
        
        x_span = x_max - x_min
        y_span = y_max - y_min

        scaled = (y_span / x_span) * (input - x_min)
        shifted = scaled + y_min
        return shifted

    async def move_mouse(self, max_idle_cycles=80, mouse_type = "ACCEL", hall_pass: asyncio.Event = None):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''

        idle_thresh = 5.0 # speed below which is considered idle
        min_run_cycles = 1 * self.specs['num_samples']
        
        #scale is "base" for acceleration - do adjustments here
        scale = None # MUST set scale

        """ TODO: have these values arise out of config """
        # dps limits for slow vs mid vs fast movement        
        slow_thresh = 20.0
        fast_thresh = 240.0

        # scale amount for slow and fast movement, mid is linear translation between
        slow_scale = 0.2
        fast_scale = 3.0

        # number of cycles currently idled (reset to 0 on motion)
        idle_count = 0

        # number of cycles run in total
        cycle_count = 0
        ti = sp.ticks_ms()
        while True:
            # print(".")
            await self.events.move_mouse.wait() # only execute when move_mouse is set
            
            await self.events.data_ready.wait() # at top of cycle, wait for an imu read
            self.events.data_ready.clear()

            if cycle_count == 0:
                print("Mouse is live: ")

            cycle_count += 1    # count cycles

            # isolate x and y axes so they can be changed later with different orientations
            x_mvmt = self.gy
            y_mvmt = self.gz
            
            # calculate magnitude and angle for linear scaling
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = atan2(y_mvmt, x_mvmt)
            
            # pure linear mouse, move number of pixels equal to number of degrees rotation
            if(mouse_type == "LINEAR"):
                scale = 1.0

            # mouse with dynamic acceleration for fine and coarse control
            if(mouse_type == "ACCEL"):
                scale = Cato.translate(slow_thresh, fast_thresh, slow_scale, fast_scale, mag)

            # Begin idle checking -- only after minimum duration
            if(cycle_count >= min_run_cycles ):
                
                if cycle_count == min_run_cycles:
                    print(f"\tmin_duration_reached at: {cycle_count} cycles")
                    print('\tnow watching for idle')
    
                if( mag <= idle_thresh ): # if too slow
                    # if (idle_count == 0): # count time of idle to finish (design util)
                        # print("\tidle detected, count begun")
                    idle_count += 1

                else:
                    # print("\tactivity resumed: idle counter reset")
                    idle_count = 0

                if idle_count >= max_idle_cycles: # if sufficiently idle, clear move_mouse
                    self.events.move_mouse.clear()
                    self.events.mouse_done.set()
                    cycle_count = 0
                    print("\tidled: exiting")
                    try:
                        hall_pass.set()
                    except:
                        pass
            
            # trig scaling of mouse x and y values
            x = int( scale * mag * cos(ang) )
            y = int( scale * mag * sin(ang) )
            # print(".")
            self.blue.mouse.move(x, y, 0)

        #print( "    Time idled: {} s".format( time.monotonic() - t_idle_start) )

    async def idle_checking(self):
        # TODO
        pass
    
    async def _scroll(self, hall_pass: asyncio.Event = None):
        print("_SCROLL: set scroll")
        self.events.scroll.set()
        print("_SCROLL: awaiting scroll_done")
        
        await self.events.scroll_done.wait()
        self.events.scroll_done.clear()
        print("_SCROLL: recieve and clear scroll_done ")

        if hall_pass is not None:
            hall_pass.set()

    async def scroll(self, hall_pass: asyncio.Event = None):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        
        z = 0.0 #value to integrate to manage scroll
        dt = 1.0 / self.specs["freq"]
        scale = 1.0 # slow down kids

        while True:
            await self.events.scroll.wait() # block if not set
            slow_down = 10
            for i in range(slow_down):
                await self.events.data_ready.wait() #read_imu
                self.events.data_ready.clear()
            
            z += (-1) * scale * self.gz * dt

            # print(f"z: {z}")
            self.blue.mouse.move(0, 0, int(z))

            if( abs(self.gy) > 30.0 ):
                print("\tScroll Broken")
                z = 0.0
                self.events.scroll_done.set()
                self.events.scroll.clear()
                if hall_pass is not None:
                    print("\tSCROLL: Scroll_done set & hall_pass set")
                    hall_pass.set()
    
    async def _scroll_lr(self, hall_pass: asyncio.Event = None):
        self.blue.k.press(Keycode.LEFT_SHIFT)
        self.events.scroll_lr.set()
        await self.events.scroll_lr_done.wait()
        self.events.scroll_lr_done.clear()
        if hall_pass is not None:
            hall_pass.set()
        self.blue.k.release(Keycode.LEFT_SHIFT)

    #shift + scroll = lateral scroll on MOST applications
    async def scroll_lr(self, hall_pass: asyncio.Event = None):
        ''' shift + scroll = lateral scroll on MOST applications
            laterally scroll until exit condition
        '''
        ''' scrolls the mouse until sufficient exit condition is reached '''
        
        y = 0.0 #value to integrate to manage scroll
        dt = 1.0 / self.specs["freq"]
        scale = 1.0 # slow down kids

        while True:
            # Fprint(".")
            await self.events.scroll_lr.wait() # block if not set
            slow_down = 4
            for i in range(slow_down):
                await self.events.data_ready.wait() #read_imu
                self.events.data_ready.clear()
            
            y += (-1) * scale * self.gy * dt

            # print(f"z: {z}")
            self.blue.mouse.move(0, 0, int(y))

            if( abs(self.gz) > 40.0 ):
                print("\tScroll Broken")
                y = 0.0
                self.events.scroll_lr_done.set()
                self.events.scroll_lr.clear()
                if hall_pass is not None:
                    print("\tSCROLL_LR: Scroll_done set & hall_pass set")
                    hall_pass.set()

    async def left_click(self, hall_pass: asyncio.Event = None): # "Does the send wait for acknowledgement"
        # determine if async or not
        # can have BLE writes w/wo ack -- send and pray vs confirm
        # time the routine uS ok, mS bad
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def double_click(self, hall_pass: asyncio.Event = None):
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()


    async def right_click(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.RIGHT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def middle_click(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.MIDDLE_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def left_click_drag(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        print("Left click")
        self.left_press()
        print("Drag")
        await self.move_mouse()
        self.left_release()

    async def right_click_drag(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.right_press()
        await self.move_mouse()
        self.right_release()

    async def middle_click_drag(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.middle_press()
        await self.move_mouse()
        self.middle_release()

    async def left_press(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.LEFT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def left_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.LEFT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def right_press(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.RIGHT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def right_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.RIGHT_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def middle_press(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.MIDDLE_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def middle_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.MIDDLE_BUTTON)
        if hall_pass is not None:
            hall_pass.set()

    async def all_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.mouse.release_all()
        if hall_pass is not None:
            hall_pass.set()
        
    # cato keyboard actions
    async def press_enter(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.ENTER)
        self.blue.k.release(Keycode.ENTER)
        if hall_pass is not None:
            hall_pass.set()

    # ToDo, the rest of the keyboard buttons

    # DATA COLLECTION TASK:
    @property
    def last_read(self):
        return self.time_hist[self.buf]
    
    @last_read.setter
    def last_read(self, value):
        self.time_hist[self.buf] = value

    @property
    def o_str(self):
        return "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f}".format(self.last_read, self.ax, self.ay, self.az, self.gx, self.gy, self.gz)

    async def _wait_for_motion(self, hall_pass: asyncio.Event = None):
        print("1")
        self.events.wait_for_motion.set()
        await self.events.wait_for_motion_done.wait()
        print("2")
        if hall_pass is not None:
            hall_pass.set()
        print("3")
    
    async def wait_for_motion(self, thresh = 105, *, num = -1, hall_pass: asyncio.Event = None):
        """
            thresh      = threshold of motion to break loop             \n
            num         = number of cycles max before return False      \n
                -1          = indefinite wait for motion                \n
                Positive Int= breaks after num loops
        """
        cycles = 0 # count number of waited cycles
        while True:
            await self.events.wait_for_motion.wait()

            await self.events.data_ready.wait()
            self.events.data_ready.clear()

            cycles += 1

            val = self.gx ** 2 + self.gy ** 2 + self.gz ** 2
            
            # BREAK CONDN 1: SIGNIFICANT MOTION
            if val > thresh:
                print('WAIT: clear wait_for_motion')
                self.events.wait_for_motion.clear()
                
                print("WAIT: set sig_motion")
                self.events.sig_motion.set()
            
            #Break CONDN 2: TIMEOUT
            if num != -1:
                if cycles > num:
                    self.events.wait_for_motion.clear()
                    print("WAIT: clear wait_for_motion")
                    
                    self.events.sig_motion.clear()
                    print("WAIT: timeout -> clear sig_motion")

            # exiting cleanup
            if not self.events.wait_for_motion.is_set():
                self.events.wait_for_motion_done.set()
                print("WAIT: set wait_for_motion_done")
                cycles = 0

                if hall_pass is not None:
                    hall_pass.set()
                    print("WAIT: hall_pass set")
                    
    # # NEEDS REWRITE
    # def collect_n_gestures(self, n=1):
    #     for file in os.listdir("/data"):
    #         try:
    #             print("removing existing copy of {}".format(file))
    #             os.remove("data/{}".format(file))
    #         except:
    #             print("could not remove {}".format(file))
    #     for i in range(n):
    #         my_file = "data/data{:02}.txt".format(i)
    #         print("Ready to read into: {}".format(my_file))
    #         print("    Waiting for motion")
    #         self.wait_for_motion()
    #         print("Capturing")
    #         self.read_gesture()
    #         print("Done")
    #         my_string = ""
    #         chunks = 0
    #         chunksize = 10
    #         with io.open(my_file, "w") as f:
    #             temp = ""
    #             print("{} opened".format(my_file))
    #             for sample in range(self.specs["num_samples"]):
    #                 b_pos = (self.buf + sample + 1) % self.specs["num_samples"]
    #                 temp = "%d,%f,%f,%f,%f,%f,%f" % (self.time_hist[b_pos],    
    #                                                 self.ax_hist[b_pos],    self.ay_hist[b_pos],    self.az_hist[b_pos],
    #                                                 self.gx_hist[b_pos],    self.gy_hist[b_pos],    self.gz_hist[b_pos])
    #                 chunks += 1
    #                 print(temp, file = f)
    #                 if chunks % chunksize == 0:
    #                     print('', file=f, flush=True, end='')
    #                 # f.write("%d,%f,%f,%f,%f,%f,%f\r\n" % (self.time_hist[b_pos],    self.ax_hist[b_pos],    self.ay_hist[b_pos],    self.az_hist[b_pos],  \
    #                 #    self.gx_hist[b_pos],    self.gy_hist[b_pos],    self.gz_hist[b_pos]) )
    #             #f.write(my_string)
    #             #print(my_string)
    #             f.close()
    #         print("{} written".format(my_file))

    async def collect_garbage(self):
        while True:
            print("COLLECT_GARBAGE: awaiting collect_garbage")
            await self.events.collect_garbage.wait()
            self.events.collect_garbage.clear()
            print("COLLECT_GARBAGE: recieved and cleared collect_garbage")
            
            gc.collect()
            print("COLLECT_GARBAGE: collected garbage and SET garbage_done")
            self.events.collect_garbage_done.set()
            
