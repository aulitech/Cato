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
import alarm

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from math import sqrt, atan2, sin, cos, pow, pi
import array
import supervisor as sp

from battery import Battery
from imu import LSM6DS3TRC

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
    NONE = 0
    UP = 1
    DOWN = 2
    RIGHT = 3
    LEFT = 4
    ROLL_R = 5
    ROLL_L = 6
    SHAKE_YES = 7
    SHAKE_NO = 8

class Events:
    control_loop            = asyncio.Event()   # enable flow through main control loop - set this in detect event
    move_mouse              = asyncio.Event()   # move the mouse
    mouse_done              = asyncio.Event()   # indicates mouse movement has finished
    scroll                  = asyncio.Event()   # scroll the screen
    scroll_done             = asyncio.Event()   # indicates scroll has finished
    scroll_lr               = asyncio.Event()   # scroll left to right
    scroll_lr_done          = asyncio.Event()   # indicates that scroll_lr has completed
    wait_for_motion         = asyncio.Event()   # wait_for_motion
    wait_for_motion_done    = asyncio.Event()   # wait-for-motion exit indicator
    sig_motion              = asyncio.Event()   # indicates that there has been significant motion during wait_for_motion's window
    stream_imu              = asyncio.Event()   # stream data from the imu onto console -- useful for debugging
    detect_event            = asyncio.Event()   # triggers detection of Cato gesture
    idle                    = asyncio.Event()   # triggered when no events change for some time

# I can't make the "Neuton: Constructing buffer from ... go away unless I crack open the circuitpython uf2"
neuton_outputs = array.array( "f", [0, 0, 0, 0, 0, 0, 0, 0] )

def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

class Cato:
    ''' Main Class of Cato Gesture Mouse '''
    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        mem("Cato init start")
        try: # load config -- restart on fail
            with open("config.json", 'r') as f:
                self.config = json.load(f)
        except:
            mc.reset() # nominally I'd like this to write some kind of "default config" from boot

        #specification for operation
        self.specs = {
            "freq" : 104.0, # imu measurement frequency (hz)
            "g_dur": 0.75   # gesture duration (s)
        }

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish

        # battery managing container
        self.battery = Battery()

        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        
        self.blue = BluetoothControl.BluetoothControl()

        self.state = ST.IDLE
        self.st_matrix = [] # Parse strings from config into json for st_matrix proper
        for row in self.config['st_matrix']:
            tmp_row = []
            for entry in row:
                cmd = f"self.{entry}"
                tmp_row.append( eval(cmd, {"self":self}) ) #here, bind function name strings to function handles
            self.st_matrix.append(tmp_row)

        self.gx_trim, self.gy_trim, self.gz_trim = 0, 0, 0

        self.imu = LSM6DS3TRC()

        # functions to 'keep on hand'
        self.tasks = {
            #"wait_for_motion"   : asyncio.create_task(self.wait_for_motion()),
            #"move_mouse"        : asyncio.create_task(self.move_mouse()),
            #"detect_event"      : asyncio.create_task(self.detect_event()),
            "monitor_battery"   : asyncio.create_task(self.monitor_battery()),
            # "scroll"            : asyncio.create_task(self.scroll()),
            # "sleep"             : asyncio.create_task(self.go_to_sleep()),
        }
        if( self.config['operation_mode'] == "pointer"):
            self.tasks.update(
                {
                    'move_mouse' : asyncio.create_task( self.move_mouse(forever = True) )
                }
            )
        self.tasks.update(self.imu.tasks)   # functions for the imu
        self.tasks.update(self.blue.tasks)  # functions for bluetooth

        self.n = Neuton(outputs=neuton_outputs)
        self.gesture = EV.NONE

    @property
    def gx(self):
        return self.imu.gx
    
    @property
    def gy(self):
        return self.imu.gy

    @property
    def gz(self):
        return self.imu.gz

    @property
    def ax(self):
        return self.imu.ax

    @property
    def ay(self):
        return self.imu.ay

    @property
    def az(self):
        return self.imu.az
    
    
    async def go_to_sleep(self):
        await asyncio.sleep(15)
        self.imu.single_tap_cfg()
        self.tasks['interrupt'].cancel()
        await asyncio.sleep(1)
        pin_alarm = alarm.pin.PinAlarm(pin = board.IMU_INT1, value = True)
        print("LIGHT SLEEP")
        alarm.light_sleep_until_alarms(pin_alarm)
        print("WOKE UP")
        self.imu.data_ready_on_int1_setup()
        del(pin_alarm) # release imu_int1
        await asyncio.sleep(1)
        self.tasks['interrupt'] = asyncio.create_task( self.imu.interrupt() )
        while True:
            await asyncio.sleep(10)

    async def monitor_battery(self):
        while True:
            await asyncio.sleep(10)
            self.blue.battery_service.level = self.battery.level

    async def _move_mouse(self, hall_pass: asyncio.Event = None):
        Events.move_mouse.set()
        await Events.mouse_done.wait()
        Events.mouse_done.clear()
        hall_pass.set()
    
    async def block_on(self, coro):
        '''
            await target function having uncertain runtime which also needs to use async imu functionality  \n
            coro: Coroutine or other awaitable
        '''
        mem("Block -- Top")
        await coro(self.hall_pass)
        await self.hall_pass.wait()
        self.hall_pass.clear()
        mem("block_on -- finish")
    
    async def detect_event(self): 
        ''' calls to gesture detection libraries '''
        gesture = EV.NONE
        while True:
            await Events.detect_event.wait()
            Events.detect_event.clear()

            await self.shake_cursor()

            print("Detect Event: waiting for motion")
            await self.block_on(self._wait_for_motion)
            print("Detect Event: Motion recieved")

            motion_detected = Events.sig_motion.is_set()
            
            if motion_detected:
                Events.sig_motion.clear()

                neuton_needs_more_data = True
                arr = array.array( 'f', [0]*6 )
                
                while( neuton_needs_more_data ):
                    await self.imu.wait()
                    arr[0] = self.ax
                    arr[1] = self.ay
                    arr[2] = self.az
                    arr[3] = self.gx
                    arr[4] = self.gy
                    arr[5] = self.gz
                    neuton_needs_more_data = self.n.set_inputs( arr )

                gesture = self.n.inference() + 1 # plus one ensures that 0 event is "none"
                confidence = max(neuton_outputs)

                confidence_thresh = 0.80
                if confidence < confidence_thresh:
                    gesture = EV.NONE

            else:
                gesture = EV.NONE

            target_fn = self.st_matrix[gesture][self.state]
            print(f"Detect Event -- Dispatching: {target_fn.__name__}")

            await self.block_on(target_fn)
            print("Detect Event: Finished Dispatching")

            Events.control_loop.set()
      
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
        mv_size = 8
        num_wiggles = 1
        moves = [
            # L R R L (horizontal wiggle)
            (-mv_size,  0,          0),
            (mv_size,   0,          0),
            (mv_size,   0,          0),
            (-mv_size,  0,          0),

            # U D D U (vert wiggle)
            (0,         mv_size,    0),
            (0,         -mv_size,   0),
            (0,         -mv_size,   0),
            (0,         mv_size,    0),
        ]

        for wiggle in range(num_wiggles):
            for move in moves:
                for _ in range(4):
                    await asyncio.sleep(0.03)
                    self.blue.mouse.move( *move )
        if hall_pass is not None:
            hall_pass.set()

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
    

    async def move_mouse(self, max_idle_cycles=80, mouse_type = "ACCEL", forever: bool = False):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''
        mem("move_mouse -- pre settings load")
        
        cfg = self.config['mouse']

        idle_thresh = cfg['idle_thresh'] # speed below which is considered idle  
        min_run_cycles = cfg['min_run_cycles']
        
        #scale is "base" for acceleration - do adjustments here
        scale = 1.0
        usr_scale = cfg['scale'] #user multiplier

        """ TODO: have these values arise out of config """
        # dps limits for slow vs mid vs fast movement        
        slow_thresh = cfg['slow_thresh']
        fast_thresh = cfg['fast_thresh']

        # scale amount for slow and fast movement, mid is linear translation between
        slow_scale = cfg['slow_scale']
        fast_scale = cfg['fast_scale']

        # number of cycles currently idled (reset to 0 on motion)
        idle_count = 0

        # number of cycles run in total
        cycle_count = 0
        dx = 0
        dy = 0
        dscroll = 0

        mem("post_cfg") # At this point, between pre and post, we lost only 100bytes

        while True:
            if not Events.move_mouse.is_set():
                print("move mouse -- awaiting")
            await Events.move_mouse.wait() # only execute when move_mouse is set
            await self.imu.wait()

            if cycle_count == 0:
                print("Mouse is live: ")
                mem("Start of Mouse operation")

            cycle_count += 1    # count cycles

            # isolate x and y axes so they can be changed later with different orientations
            x_mvmt = self.gy
            y_mvmt = self.gz

            # calculate magnitude and angle for linear scaling
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = atan2(y_mvmt, x_mvmt)
            
            # pure linear mouse, move number of pixels equal to number of degrees rotation
            if(mouse_type == "LINEAR"):
                pass

            # mouse with dynamic acceleration for fine and coarse control
            if(mouse_type == "ACCEL"):
                scale = Cato.translate(slow_thresh, fast_thresh, slow_scale, fast_scale, mag)

            # Begin idle checking -- only after minimum duration
            if(cycle_count >= min_run_cycles and forever == False):
                if( mag <= idle_thresh ): # if mouse move speed below threshold
                    idle_count += 1 #iterate
                else: # otherwise reset
                    idle_count = 0

                if idle_count >= max_idle_cycles: # if sufficiently idle, clear move_mouse
                    print("\tMouse Exit")
                    Events.move_mouse.clear()
                    Events.mouse_done.set()

                    idle_count = 0
                    cycle_count = 0

            mag = mag * usr_scale
            # trig scaling of mouse x and y values
            dx = int( scale * mag * cos(ang) )
            dy = int( scale * mag * sin(ang) )

            self.blue.mouse.move(dx, dy, dscroll)

    async def click(self):
        while True:
            await self.imu.wait()
            await self.left_click()

    async def _scroll(self, hall_pass: asyncio.Event = None):
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        hall_pass.set()

    async def scroll(self, hall_pass: asyncio.Event = None):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        
        z = 0.0 #value to integrate to manage scroll
        dt = 1.0 / self.specs["freq"]
        scale = 1.0 # slow down kids

        while True:
            await Events.scroll.wait() # block if not set
            slow_down = 10
            for i in range(slow_down):
                await self.imu.wait()
            
            z += (-1) * scale * self.gz * dt

            # print(f"z: {z}")
            # print( id(self.blue.mouse) )
            self.blue.mouse.move(0, 0, int(z))

            if( abs(self.gy) > 30.0 ):
                print("\tScroll Broken")
                z = 0.0
                Events.scroll_done.set()
                Events.scroll.clear()
                if hall_pass is not None:
                    print("\tSCROLL: Scroll_done set & hall_pass set")
                    hall_pass.set()
    
    async def _scroll_lr(self, hall_pass: asyncio.Event = None):
        self.blue.k.press(Keycode.LEFT_SHIFT)
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        self.blue.k.release(Keycode.LEFT_SHIFT)

    async def left_click(self, hall_pass: asyncio.Event = None): # "Does the send a wait for acknowledgement"
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

    @property
    def o_str(self):
        return "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f}".format(self.last_read, self.ax, self.ay, self.az, self.gx, self.gy, self.gz)

    async def _wait_for_motion(self, hall_pass: asyncio.Event = None):
        Events.wait_for_motion.set()
        await Events.wait_for_motion_done.wait()
        Events.wait_for_motion_done.clear()
        hall_pass.set()

    async def wait_for_motion(self, thresh = 105, *, num = -1):
        #NOTE: THIS COULD BE MADE MUCH CHEAPER WITH THE INT1_SIGN_MOT INTERRUPT!
        """
            thresh      = threshold of motion to break loop             \n
            num         = number of cycles max before return False      \n
                -1          = indefinite wait for motion                \n
                Positive Int= breaks after num loops
        """
        cycles = 0 # count number of waited cycles
        val = 0.0
        while True:
            # print("A: ", gc.mem_free())
            
            await Events.wait_for_motion.wait()
            # print("wait_for_motion triggered")
            # print("B: ", gc.mem_free())
            
            await self.imu.wait()
            # print("C: ", gc.mem_free())
            cycles += 1

            val = self.gx ** 2 + self.gy ** 2 + self.gz ** 2

            # BREAK CONDN 1: SIGNIFICANT MOTION
            if val > thresh:
                Events.wait_for_motion.clear()
                Events.sig_motion.set()
            #Break CONDN 2: TIMEOUT
            if num != -1:
                if cycles > num:
                    Events.wait_for_motion.clear()
                    Events.sig_motion.clear()
            # print("D: ", gc.mem_free())
            # exiting cleanup
            if not Events.wait_for_motion.is_set():
                exit_reason = "MOTION" if Events.sig_motion.is_set() else "TIMEOUT"
                print( f"WAIT FOR MOTION: EXIT : { exit_reason }" )
                Events.wait_for_motion_done.set()
                cycles = 0
            # print("E: ", gc.mem_free())
            # print("")
                    
    # NEEDS REWRITE
    def collect_n_gestures(self, n=1):
        """
        while True:
            await (SOME SIGNAL THAT IT"S TIME TO COLLECT DATA):
            clear that signal

            await significant motion (method Events.wait_for_motion.set())
            wait for motion detection to break
            clera the signal that motion detection happened

            read the correct number of samples

            write them to the board

        """

        # for file in os.listdir("/data"):
        #     try:
        #         print("removing existing copy of {}".format(file))
        #         os.remove("data/{}".format(file))
        #     except:
        #         print("could not remove {}".format(file))
        for i in range(n):
            my_file = "data/data{:02}.txt".format(i)
            print("Ready to read into: {}".format(my_file))
            print("    Waiting for motion")
            self.wait_for_motion() # await motion, when triggered, do capture
            print("Capturing")
            self.read_gesture() # reads one full buffer into the history
            print("Done")
            my_string = ""
            chunks = 0
            chunksize = 10
            with io.open(my_file, "w") as f:
                temp = ""
                print("{} opened".format(my_file))
                for sample in range(self.specs["num_samples"]):
                    b_pos = (self.buf + sample + 1) % self.specs["num_samples"]
                    temp = "%d,%f,%f,%f,%f,%f,%f" % (self.time_hist[b_pos],    
                                                    self.ax_hist[b_pos],    self.ay_hist[b_pos],    self.az_hist[b_pos],
                                                    self.gx_hist[b_pos],    self.gy_hist[b_pos],    self.gz_hist[b_pos])
                    chunks += 1
                    print(temp, file = f)
                    if chunks % chunksize == 0:
                        print('', file=f, flush=True, end='')
                    # f.write("%d,%f,%f,%f,%f,%f,%f\r\n" % (self.time_hist[b_pos],    self.ax_hist[b_pos],    self.ay_hist[b_pos],    self.az_hist[b_pos],  \
                    #    self.gx_hist[b_pos],    self.gy_hist[b_pos],    self.gz_hist[b_pos]) )
                #f.write(my_string)
                #print(my_string)
                f.close()
            print("{} written".format(my_file))

