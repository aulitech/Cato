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

from StrCharacteristicService import config
from StrCharacteristicService import DebugStream

##TEMP IMPORTS

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
    collect_gestures        = asyncio.Event()   #working on it

# I can't make the "Neuton: Constructing buffer from ... go away unless I crack open the circuitpython uf2"
neuton_outputs = array.array( "f", [0, 0, 0, 0, 0, 0, 0, 0] )

def mem( loc = "" ):
    DebugStream.println(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

class Cato:

    ''' Main Class of Cato Gesture Mouse '''
    config = None

    gesture_key = [
        "Nod Down",
        "Nod Up",
        "Nod Right",
        "Nod Left",
        "Tilt Right",
        "Tilt Left",
        "Shake Vertical",
        "Shake Horizontal"
    ]

    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        DebugStream.println("Cato init: start")

        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        
        #DebugStream.println(config)
       
        if(config["operation_mode"] >=20)&(bool(mc.nvm[0])):
            DebugStream.println("WARNING: Collect Gesture mode will not record data")

        #specification for operation
        self.specs = {
            "freq" : 104.0, # imu measurement frequency (hz)
            "g_dur": 0.75   # gesture duration (s)
        }

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish

        # battery managing container
        self.battery = Battery()

        self.blue = BluetoothControl.BluetoothControl()

        self.state = ST.IDLE
        self.st_matrix = []
        for row in config['st_matrix']:
            tmp_row = []
            for entry in row:
                cmd = f"self.{entry}"
                tmp_row.append( eval(cmd, {"self":self}) )
            self.st_matrix.append(tmp_row)

        self.gx_trim, self.gy_trim, self.gz_trim = 0, 0, 0

        self.imu = LSM6DS3TRC()

        # blocking functions enabled by events
        if(config["operation_mode"] == 0):
            self.tasks = {
                "wait_for_motion"   : asyncio.create_task(self.wait_for_motion()),
                "move_mouse"        : asyncio.create_task(self.move_mouse()),
                "detect_event"      : asyncio.create_task(self.detect_event()),
                "monitor_battery"   : asyncio.create_task(self.monitor_battery()),
                "scroll"            : asyncio.create_task(self.scroll()),
            "sleep"             : asyncio.create_task(self.go_to_sleep()),
            }
        elif(config["operation_mode"] >=20):
            self.tasks = {
                "wait_for_motion"   : self.wait_for_motion(),
                "collect_gestures"  : self.collect_gestures(gestID = config["operation_mode"]-20)
            }
        elif(config["operation_mode"] == 10):
            self.tasks = {
                "test_loop"         : self.test_loop()
            }
        self.tasks.update(self.imu.tasks)   # functions for the imu
        self.tasks.update(self.blue.tasks)  # functions for bluetooth

        self.n = Neuton(outputs=neuton_outputs)
        self.gesture = EV.NONE
    
    async def reboot():
        mc.reset()

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
            
            gc.collect()

            DebugStream.println("Detect Event: waiting for motion")
            await self.block_on(self._wait_for_motion)
            DebugStream.println("Detect Event: Motion recieved")

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
            DebugStream.println(f"Detect Event -- Dispatching: {target_fn.__name__}")

            await self.block_on(target_fn)
            DebugStream.println("Detect Event: Finished Dispatching")

            Events.control_loop.set()
      
    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    async def noop(self, hall_pass: asyncio.Event = None):
        ''' no operation '''
        DebugStream.println("nooping")
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
    

    async def move_mouse(self, max_idle_cycles=80, mouse_type = "ACCEL"):
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
            # DebugStream.println(".")
            if not Events.move_mouse.is_set():
                DebugStream.println("move mouse -- awaiting")
            
            # DebugStream.println("A: ", gc.mem_free() )
            await Events.move_mouse.wait() # only execute when move_mouse is set
            # DebugStream.println("B: ", gc.mem_free() )
            await self.imu.wait()
            # print("2")
            # DebugStream.println("C: ", gc.mem_free() )
            # DebugStream.println("C2: ", gc.mem_free() )
            if cycle_count == 0:
                DebugStream.println("Mouse is live: ")
                mem("Start of Mouse operation")
            # DebugStream.println("D: ", gc.mem_free() ) # f string substitution eats 60 bytes of data...
            # DebugStream.println("D2: ", gc.mem_free() )
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
            # DebugStream.println("A: ", gc.mem_free() )
            # mouse with dynamic acceleration for fine and coarse control
            if(mouse_type == "ACCEL"):
                scale = Cato.translate(slow_thresh, fast_thresh, slow_scale, fast_scale, mag)
            # Begin idle checking -- only after minimum duration
            if(cycle_count >= min_run_cycles ):
                if( mag <= idle_thresh ): # if too slow
                    # if (idle_count == 0): # count time of idle to finish (design util)
                        # DebugStream.println("\tidle detected, count begun")
                    idle_count += 1
                else:
                    # DebugStream.println("\tactivity resumed: idle counter reset")
                    idle_count = 0

                if idle_count >= max_idle_cycles: # if sufficiently idle, clear move_mouse
                    DebugStream.println("\tMouse Exit")
                    Events.move_mouse.clear()
                    Events.mouse_done.set()

                    idle_count = 0
                    cycle_count = 0
                    # DebugStream.println(f"post-reset cycle count: {cycle_count}")
            # DebugStream.println("A: ", gc.mem_free() )
            mag = mag * usr_scale
            # trig scaling of mouse x and y values
            dx = int( scale * mag * cos(ang) )
            dy = int( scale * mag * sin(ang) )

            # mi = gc.mem_free()
            self.blue.mouse.move(dx, dy, dscroll)
            # DebugStream.println("E: ", gc.mem_free() )
            # mf = gc.mem_free()

            # if (mf - mi > 0):
            #     DebugStream.println("Memory eaten by blue mouse move")
            #     DebugStream.println(mf - mi)
            # DebugStream.println("")
            
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

            # DebugStream.println(f"z: {z}")
            # DebugStream.println( id(self.blue.mouse) )
            self.blue.mouse.move(0, 0, int(z))

            if( abs(self.gy) > 30.0 ):
                DebugStream.println("\tScroll Broken")
                z = 0.0
                Events.scroll_done.set()
                Events.scroll.clear()
                if hall_pass is not None:
                    DebugStream.println("\tSCROLL: Scroll_done set & hall_pass set")
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
        DebugStream.println("Left click")
        self.left_press()
        DebugStream.println("Drag")
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
            # DebugStream.println("A: ", gc.mem_free())
            
            await Events.wait_for_motion.wait()
            # DebugStream.println("wait_for_motion triggered")
            # DebugStream.println("B: ", gc.mem_free())
            
            await self.imu.wait()
            # DebugStream.println("C: ", gc.mem_free())
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
            # DebugStream.println("D: ", gc.mem_free())
            # exiting cleanup
            if not Events.wait_for_motion.is_set():
                exit_reason = "MOTION" if Events.sig_motion.is_set() else "TIMEOUT"
                DebugStream.println( f"WAIT FOR MOTION: EXIT : { exit_reason }" )
                Events.wait_for_motion_done.set()
                cycles = 0
            # DebugStream.println("E: ", gc.mem_free())
            # DebugStream.println("")
            

    async def collect_gestures(self, logName = "log.txt", n = 10, gestID = 0, winSize = 76):
        from StrCharacteristicService import SCS
        DebugStream.println("+ collect_gestures")
        await self.blue.is_connected.wait()
        if(mc.nvm[1]):
            SCS.collGestUUID = "WARNING: Cato did not bott selfwritable.  Values will not be recorded"
            DebugStream.println("WARNING: Cato did not bott selfwritable.  Values will not be recorded")
        await asyncio.sleep(3)

        DebugStream.println("Collecting Gestures")
        gest_timer = asyncio.Event()
        DebugStream.println(SCS.collGestUUID)
        for i in range(n):
            hist = []
            maxGest = list
            maxAbs = 0

            # gather data from imu for 5sec
            c = 0
            start = 0
            counter = int

            SCS.collGestUUID = "Ready for Input"
            while(SCS.collGestUUID == "Ready for Input"):
                await asyncio.sleep(0)
            SCS.collGestUUID = "Input Recieved"
            while(not gest_timer.is_set()):
                await self.imu.wait()
                hist.append((self.ax, self.ay, self.az, self.gx, self.gy, self.gz, gestID))
                # if(c == 0):
                #     DebugStream.println(",\t".join(str(v) for v in hist[len(hist)-1]))
                # c = (c+1)%32

                if(len(hist) == winSize):
                    maxGest = hist.copy()
                    maxAbs = maxGest[int(winSize/2)]
                    maxAbs = maxAbs[0]**2 + maxAbs[1]**2+maxAbs[2]**2
                    asyncio.create_task(self.countN(gest_timer, 5))  # Timer starts here
                    start = time.time()
                    counter = 0
                    DebugStream.println("Perform Gesture: ",Cato.gesture_key[gestID])
                    SCS.collGestUUID = "Perform Gesture: "+str(gestID)
                
                ##could check max acc as it's read to cut mem by 1/4 (would require splitting maxGest into pre/post queues)
                elif(len(hist) > winSize):
                    hist.pop(0)
                    currMid = hist[int(winSize/2)]
                    currAbs = currMid[3]**2 + currMid[4]**2 + currMid[5]**2
                    #DebugStream.println(currMid)
                    DebugStream.println(currAbs, "<", maxAbs)
                    if(currAbs > maxAbs):
                        DebugStream.println("New Max Read")
                        SCS.collGestUUID = "New Max Read"
                        maxAbs = currAbs
                        maxGest = hist.copy()

                    if(counter < round(time.time() -start)):
                        counter = round(time.time()-start)
                        DebugStream.println(counter)
            gest_timer.clear()

            # record data
            try:
                with open(logName, 'a') as log:
                    SCS.collGestUUID = "Logging Max"
                    DebugStream.println("Writing to",logName)
                    while(len(maxGest) > 0):
                        d = maxGest.pop(0)
                        log.write(",".join(str(v) for v in d))
                        log.write("\n")
            except OSError as oser:
                SCS.collGestUUID = "Gestures cannot be recorded"
                continue
        
        SCS.collGestUUID = "Gesture Collection Completed"
        DebugStream.println("Gesture Collection Completed")

        asyncio.create_task(self.countN(gest_timer, 5))
        await gest_timer.wait()

    """
    async def collect_gestures_keyb(self, logName = "log.txt", n = 2, gestID = 0, winSize = 76):
        await self.blue.is_connected.wait()
        #await self.events.collect_gestures.wait()
        DebugStream.println("Bluetooth Connected!")
        await asyncio.sleep(2)
        with open(logName,"w"):     # open log as w to clear previous data
            pass
        
        self.bluType("Collecting Gestures")
        DebugStream.println("Collecting Gestures")
        await asyncio.sleep(2)
        gest_timer = asyncio.Event()
        for i in range(n):
            hist = []
            maxGest = list
            maxAbs = float

            # gather data from imu for 5sec
            c = 0
            start = 0
            counter = int
            while(not gest_timer.is_set()):
                await self.imu.wait()
                hist.append((self.ax, self.ay, self.az, self.gx, self.gy, self.gz, gestID))

                if(len(hist) == winSize):
                    maxGest = hist.copy()
                    maxAbs = maxGest[int(winSize/2)]
                    maxAbs = maxAbs[0]**2 + maxAbs[1]**2+maxAbs[2]**2
                    asyncio.create_task(self.countN(gest_timer, 5))  # Timer starts here
                    start = time.time()
                    counter = 0
                    DebugStream.println("Perform Gesture: ",gestID)
                    self.bluType("Perform Gesture "+str(gestID)+"\n")
                    self.blue.k.send(34)    # type 5
                
                ##could check max acc as it's read to cut mem by 1/4 (would require splitting maxGest into pre/post queues)
                elif(len(hist) > winSize):
                    hist.pop(0)
                    currMid = hist[int(winSize/2)]                    
                    currAbs = currMid[3]**2 + currMid[4]**2 + currMid[5]**2
                    if(currAbs > maxAbs):
                        maxAbs = currAbs
                        maxGest = hist.copy()

                    if(counter < round(time.time() -start)):
                        counter = round(time.time()-start)
                        DebugStream.println(counter)
                        self.blue.k.send(42)    # Backspace
                        if(counter <= 5):
                            self.bluType(str(5-counter))
            gest_timer.clear()
            self.blue.k.send(42)    # Backspace
            self.bluType("Gesture Collected\nLogging Max\n")
                
            # record data
            try:
                with open(logName,"a") as log:       ##swap to append for final?
                    DebugStream.println("Writing to",logName)
                    while(len(maxGest) > 0):
                        d = maxGest.pop(0)
                        log.write(",".join(str(v) for v in d))
                        log.write("\n")
            except:
                continue
            
        DebugStream.println("Gesture Collection Completed")
        self.bluType("Gesture Collection Completed\n")

        asyncio.create_task(self.countN(gest_timer, 5))
        await gest_timer.wait()
    

    def bluType(self, str):
        ##maybe a more robust version of this exists somewhere; worth looking into?
        for c in str:
            if(ord(c) >= 97):
                c = ord(c) - 93
            elif(ord(c) >= 65):
                self.blue.k.press(225)  #LShift
                c = ord(c) - 61
            elif(c == ' '):
                c = 44
            elif(c == '\n'):
                c = 40  #Enter
            elif(c == '0'):
                c = 39
            else:
                c = int(c) + 29
            self.blue.k.press(c)
            self.blue.k.release_all()
    """

    async def countN(self, ev, n):
        await asyncio.sleep(n)
        ev.set()


    async def test_loop(self):
        DebugStream.println("+ test_loop")
        #await self.blue.is_connected.wait()
        await asyncio.sleep(5)
        i = 0
        while(True):
            #DebugStream.println("loop: "+str(i))
            i += 1
            try:
                with open("config.json",'a') as f:
                    DebugStream.print("RO\t")
            except:
                DebugStream.print("RW\t")
            DebugStream.print(str(mc.nvm[0])+'\t'+str(mc.nvm[1])+'\n')
            DebugStream.print(config["operation_mode"])
            await asyncio.sleep(5)
