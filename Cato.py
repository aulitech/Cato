'''
Cato.py
auli.tech software to drive the Cato gesture Mouse
Written by Finn Biggs finn@auli.tech
    15-Sept-22
'''
#import sys
import board
import microcontroller as mc

# import busio
# import os
# import io
# import json
# import time
import digitalio
# import countio
import alarm

# from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
# from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
# from adafruit_hid.mouse import Mouse

from math import sqrt, atan2, sin, cos
import array
#import supervisor as sp

from battery import Battery
from imu import LSM6DS3TRC

import asyncio

import gc

from neutonml import Neuton

from StrUUIDService import config
from StrUUIDService import DebugStream

#helpers and enums

class ST():
    '''enum states'''
    IDLE = 0
    MOUSE_BUTTONS = 1
    KEYBOARD = 2


class EV(): #these are actually gestures
    gesture_key = [
        "None",
        "Nod Up",
        "Nod Down",
        "Nod Right",
        "Nod Left",
        "Tilt Right",
        "Tilt Left",
        "Shake Vertical",
        "Shake Horizontal",
        "Circle Clockwise",
        "Circle Counterclockwise"
    ]

    ''' enum events '''
    NONE = 0
    UP = 1
    DOWN = 2
    RIGHT = 3
    LEFT = 4
    ROLL_R = 5
    ROLL_L = 6
    SHAKE_YES = 7
    SHAKE_NO = 8,
    CIRCLE_CW = 9,
    CIRCLE_CCW = 10

class Events:
    control_loop            = asyncio.Event()   # enable flow through main control loop - set this in detect event
    move_mouse              = asyncio.Event()   # move the mouse
    mouse_done              = asyncio.Event()   # indicates mouse movement has finished
    scroll                  = asyncio.Event()   # scroll the screen
    scroll_done             = asyncio.Event()   # indicates scroll has finished
    scroll_lr               = asyncio.Event()   # scroll left to right
    scroll_lr_done          = asyncio.Event()   # indicates that scroll_lr has completed
    sleep                   = asyncio.Event()   # indicates time to go to sleep
    wait_for_motion         = asyncio.Event()   # wait_for_motion
    wait_for_motion_done    = asyncio.Event()   # wait-for-motion exit indicator
    feed_neuton             = asyncio.Event()   # prevent multiple instances of neuton being fed
    sig_motion              = asyncio.Event()   # indicates that there has been significant motion during wait_for_motion's window
    stream_imu              = asyncio.Event()   # stream data from the imu onto console -- useful for debugging
    mouse_event             = asyncio.Event()   # triggers detection of Cato gesture
    idle                    = asyncio.Event()   # triggered when no events change for some time

    gesture_collecting      = asyncio.Event()   # signal that collect_gestures() is currently running
    gesture_not_collecting  = asyncio.Event()
    gesture_not_collecting.set()

# Home for neuton inference
neuton_outputs = array.array( "f", [0]*len(EV.gesture_key) )

def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

from WakeDog import WakeDog

class Cato:
    ''' Main Class of Cato Gesture Mouse '''

    imu = LSM6DS3TRC()

    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        DebugStream.println("+ Cato Init")

        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        
        #DebugStream.println(config)
        mode = config["operation_mode"]
        if(mode >=20)&(bool(mc.nvm[0])):
            DebugStream.println("WARNING: Collect Gesture mode will not record data")


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

        if(mode < len(config["st_matrix"])):
            self.st_matrix = config["st_matrix"][mode]

        # Mode-dependent task spawning
        """ MODE CODE MEANINGS
                0 - 9: USER MODES
                    0:  Default Computer
                    1:  Default Television
                    2:  Forever Pointer (only pointer)
                    3:  Forever Clicker (only clicker - tap detect)
                10-19: Dev Test Modes:
                    10: Test Loop -- bluetooth print test
                x>=20: unused
        """
        if(mode == 0):
            self.tasks = {
                "wait_for_motion"   : asyncio.create_task(self.wait_for_motion()),
                "move_mouse"        : asyncio.create_task(self.move_mouse()),
                "mouse_event"       : asyncio.create_task(self.mouse_event()),
                "scroll"            : asyncio.create_task(self.scroll()),
                "sleep"             : asyncio.create_task(self.go_to_sleep()),
                "collect_gestures"  : asyncio.create_task(Cato.collect_gestures_app())
            }
        elif(mode == 1):
            self.tasks = {
                "wait_for_motion"   : asyncio.create_task(self.wait_for_motion()),
                "tv_control"        : asyncio.create_task(self.tv_control()),
                #"sleep"             : asyncio.create_task(self.go_to_sleep()),
                "collect_gestures"  : asyncio.create_task(Cato.collect_gestures_app())
            }
        
        elif(mode == 2):
            self.tasks = {
                "point" : asyncio.create_task(self.move_mouse(forever = True)),
                "sleep" : asyncio.create_task(self.go_to_sleep())
            }
        elif(mode == 3):
            self.tasks = {
                "clicker"           : asyncio.create_task(self.clicker_task()),
                "collect_gestures"  : asyncio.create_task(Cato.collect_gestures_app())
            }
        elif(mode >= 10):
            self.tasks = {
                "test_loop"         : asyncio.create_task(self.test_loop())

            }
            if(mode == 10):
                self.tasks["collect_gestures"] = asyncio.create_task(Cato.collect_gestures_app())
            elif(mode == 11):
                self.tasks["wait_for_motion"] = asyncio.create_task(Cato.wait_for_motion())
        
        self.tasks.update( {"monitor_battery"   : asyncio.create_task(self.monitor_battery())} )
        self.tasks.update(Cato.imu.tasks)   # functions for t1he imu
        self.tasks.update(self.blue.tasks)  # functions for bluetooth
        self.tasks.update(WakeDog.tasks)    # functions for waking / sleeping monitoring

        self.n = Neuton(outputs=neuton_outputs)
        self.gesture = EV.NONE

        DebugStream.println("- Cato Init")
    
    async def reboot():
        mc.reset()


    @property
    def gx(self):
        return Cato.imu.gx
    
    @property
    def gy(self):
        return Cato.imu.gy

    @property
    def gz(self):
        return Cato.imu.gz

    @property
    def ax(self):
        return Cato.imu.ax

    @property
    def ay(self):
        return Cato.imu.ay

    @property
    def az(self):
        return Cato.imu.az
    
    
    async def go_to_sleep(self):
        
        # This method sets a Cato to go to sleep - presently after exactly 15 seconds, soon to be based on inactivity
        while True:
            # await asyncio.sleep(1) # TAKE IMU READINGS BEFORE TRYING TO GO BACK TO SLEEP?
            await Events.sleep.wait()
            print("A")
            self.tasks['interrupt'].cancel() #release pin int1
            await asyncio.sleep(0.1)
            print("B")
            self.imu.single_tap_cfg() # set wakeup condn to single tap detection
            print("C")
            pin_alarm = alarm.pin.PinAlarm(pin = board.IMU_INT1, value = True) #Create pin alarm
            print("LIGHT SLEEP")
            alarm.light_sleep_until_alarms(pin_alarm)
            print("WOKE UP")
            Events.sleep.clear()
            del(pin_alarm) # release imu_int1

            Cato.imu.data_ready_on_int1_setup() #setup imu data ready

            self.tasks['interrupt'] = asyncio.create_task( Cato.imu.interrupt() )
            WakeDog.feed()
            #await asyncio.sleep(1) # TAKE IMU READINGS BEFORE TRYING TO GO BACK TO SLEEP?

    async def monitor_battery(self):
        led_pin = board.LED_GREEN
        led = digitalio.DigitalInOut(led_pin)
        led.direction = digitalio.Direction.OUTPUT
        
        while True:
            for i in range(3):
                await asyncio.sleep(0.2)
                led.value = False
                await asyncio.sleep(0.2)
                led.value = True
            await asyncio.sleep(5)
            temp = self.battery.raw_value
            # DebugStream.println(f"bat_ena True: {temp[0]}")
            await asyncio.sleep(0.1)
            # uDebugStream.println(f"bat_ena False: {temp[1]}")
            self.blue.battery_service.level = self.battery.level

    async def _move_mouse(self, hall_pass: asyncio.Event = None):
        Events.move_mouse.set()
        await Events.mouse_done.wait()
        Events.mouse_done.clear()
        hall_pass.set()

    async def center_mouse_cursor(self, hall_pass: asyncio.Event = None):
        x = config["screen_size"][0]
        y = config["screen_size"][1]
        try:
            self.blue.mouse.move(-2 * x, -2 * y)
            self.blue.mouse.move(int(0.5*x), int(0.5*y))
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in center_mouse_cursor()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()
    
    async def block_on(self, coro):
        '''
            await target function having uncertain runtime which also needs to use async imu functionality  \n
            coro: Coroutine or other awaitable
        '''
        await coro(self.hall_pass)
        await self.hall_pass.wait()
        self.hall_pass.clear()
    
    async def mouse_event(self): 
        ''' calls to gesture detection libraries '''
        while True:
            await Events.mouse_event.wait()
            Events.mouse_event.clear()
            await Events.gesture_not_collecting.wait()
            target_name = await self.gesture_interpreter()
            #print(f"\tGot \"{target_name}\" at mouse_event")
            #DebugStream.println(f"Detect Event -- Dispatching: self.{target_name}")
            await self.block_on(eval("self."+target_name, {"self":self}))
            print(f"\t \"{target_name}\" finished at mouse_event")
            
            #DebugStream.println("Detect Event: Finished Dispatching")
            Events.control_loop.set()
    
    async def tv_control(self):
        Cato.imu.data_ready_on_int1_setup()
        turbo_terminate = asyncio.Event()
        task_dict = {
            "noop"  :   None,
            "up"    :   (self.turbo_input,
                            (self.press_up, config["turbo_rate"], turbo_terminate)),
            "down"  :   (self.turbo_input,
                            (self.press_down, config["turbo_rate"], turbo_terminate)),
            "left"  :   (self.turbo_input,
                            (self.press_left, config["turbo_rate"], turbo_terminate)),
            "right" :   (self.turbo_input,
                            (self.press_right, config["turbo_rate"], turbo_terminate)),
            "enter" :   (self.press_enter,()),
            "esc"   :   (self.press_esc,()),
            "meta"  :   (self.press_meta,())
        }
        task = None
        prev_task = "noop"
        DebugStream.println("tv_control")
        while True:
            await Events.gesture_not_collecting.wait()
            task_name = await self.tv_interpreter()

            # needs a check for sigMotion upon new gestInterpreter
            # needs a check for sigMotion upon new gestInterpreter
            if(Events.sig_motion.is_set())and(task != None):
                turbo_terminate.set()
                await task
                turbo_terminate.clear()

            if(task_name != "noop"):                
                func_tuple = task_dict[task_name]
                if((func_tuple[0].__name__ != self.turbo_input.__name__) or (task_name != prev_task)):
                    task = asyncio.create_task(func_tuple[0](*func_tuple[1]))
                    prev_task = task_name
                else:
                    prev_task = "noop"
                await asyncio.sleep(0.3)
            elif(Events.sig_motion.is_set()):
                prev_task = "noop"
    
    async def dummy_event(self):
        from StrUUIDService import SUS
        SUS.collGestUUID = ""
        while(SUS.collGestUUID == ""):
            await asyncio.sleep(0.1)
        g = int(SUS.collGestUUID)
        DebugStream.println(g,":\t",self.st_matrix[g][0])
        return self.st_matrix[g][0]
    
    # defunct interpreter method
    async def gesture_interpreter_alt(self):
        gesture = EV.NONE
        # DebugStream.println("Detect Event: waiting for motion")
        await self.block_on(self._wait_for_motion)
        # DebugStream.println("Detect Event: Motion recieved")

        motion_detected = Events.sig_motion.is_set()
        
        if motion_detected:
            DebugStream.println("Motion was detected")
            neuton_needs_more_data = True
            arr = array.array( 'f', [0]*6 )
            
            while( neuton_needs_more_data ):
                await Cato.imu.wait()
                arr[0] = self.ax
                arr[1] = self.ay
                arr[2] = self.az
                arr[3] = self.gx
                arr[4] = self.gy
                arr[5] = self.gz
                neuton_needs_more_data = self.n.set_inputs( arr )
                # DebugStream.println(f"{neuton_needs_more_data}")

            gesture = self.n.inference() + 1 # plus one ensures that 0 event is "none"
            confidence = max(neuton_outputs)

            confidence_thresh = 0.80
            if confidence < confidence_thresh:
                gesture = EV.NONE
        else:
            gesture = EV.NONE
        # self.state
        return self.st_matrix[gesture][self.state]
    

    async def gesture_interpreter(self):
        infer = EV.NONE
        gest = []
        gestLen = config["gesture_length"]
        maxMag = 0
        minThresh = config["min_gesture_threshold"]

        Events.feed_neuton.set()
        feedNeut = None
        confThresh = config["confidence_threshold"]

        # this block is experimental
        # adds a buffer period that waits for premature motion to pass
        i = 0
        gest = [0]*int(gestLen/2)
        while(i < gestLen/2):
            await Cato.imu.wait()
            gest[i] = array.array('f',[Cato.imu.ax, self.ay, self.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz])
            mag = Cato.imu.gx**2 + Cato.imu.gy**2 + Cato.imu.gz**2
            i += 1
            if(mag > minThresh):
                return self.st_matrix[EV.NONE][self.state]
        
        shakeCursor = asyncio.create_task(self.shake_cursor()) #ADD PRINT TO SHAKE CURSOR
        DebugStream.println("+ MouseEvent: Looking for Gesture")
        Events.sig_motion.clear()

        i = 0
        # sw = asyncio.create_task(Cato.stopwatch(config["gesture_window"]))
        # while(i <= gestLen/2)or(not sw.done()):
        while(i <= gestLen / 2):
            await Cato.imu.wait()
            gest.append(array.array('f',[Cato.imu.ax, self.ay, self.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz]))
            if(len(gest) > gestLen):
                gest.pop(0)
            
            currMag = Cato.imu.gx**2 + Cato.imu.gy**2 + Cato.imu.gz**2
            if(currMag > maxMag):
                maxMag = currMag
                i = 0
            
            if(maxMag >= minThresh):
                i += 1
                if(i == int(gestLen/2)):
                    feedNeut = asyncio.create_task(self.feed_neuton(gest.copy()))
            
            if(feedNeut is not None):
                if(feedNeut.done()):
                    temp = self.n.inference()+1
                    Events.feed_neuton.set()
                    DebugStream.println(neuton_outputs)
                    if(max(neuton_outputs) >= confThresh):
                        infer = temp
                    feedNeut = None
        
        if(maxMag >= minThresh):
            Events.sig_motion.set()

        await shakeCursor
        return self.st_matrix[infer][self.state]
    
    #maybe not necessary?
    async def tv_interpreter(self):
        infer = EV.NONE
        gest = []
        gestLen = config["gesture_length"]
        maxMag = 0
        minThresh = config["min_gesture_threshold"]

        Events.feed_neuton.set()
        feedNeut = None
        confThresh = config["confidence_threshold"]

        # this block is experimental
        # adds a buffer period that waits for premature motion to pass
        i = 0
        gest = [0]*int(gestLen/2)
        while(i < gestLen/2):
            await Cato.imu.wait()
            gest[i] = array.array('f',[Cato.imu.ax, self.ay, self.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz])
            mag = Cato.imu.gx**2 + Cato.imu.gy**2 + Cato.imu.gz**2
            i += 1
            if(mag > minThresh):
                i = 0
        
        DebugStream.println("+ MouseEvent: Looking for Gesture")
        Events.sig_motion.clear()

        i = 0
        # sw = asyncio.create_task(Cato.stopwatch(config["gesture_window"]))
        # while(i <= gestLen/2)or(not sw.done()):
        while(i <= gestLen / 2):
            await Cato.imu.wait()
            gest.append(array.array('f',[Cato.imu.ax, self.ay, self.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz]))
            if(len(gest) > gestLen):
                gest.pop(0)
            
            currMag = Cato.imu.gx**2 + Cato.imu.gy**2 + Cato.imu.gz**2
            if(currMag > maxMag):
                maxMag = currMag
                i = 0
            
            if(maxMag >= minThresh):
                i += 1
                if(i == int(gestLen/2)):
                    feedNeut = asyncio.create_task(self.feed_neuton(gest.copy()))
            
            if(feedNeut is not None):
                if(feedNeut.done()):
                    temp = self.n.inference()+1
                    Events.feed_neuton.set()
                    DebugStream.println(neuton_outputs)
                    if(max(neuton_outputs) >= confThresh):
                        infer = temp
                    feedNeut = None
        
        if(maxMag >= minThresh):
            Events.sig_motion.set()

        await shakeCursor
        return self.st_matrix[infer][self.state]
    
    async def feed_neuton(self, log):
        await Events.feed_neuton.wait()
        Events.feed_neuton.clear()
        DebugStream.println("Feeding Neuton")
        for data in log:
            if(not self.n.set_inputs(data)):
                break
        DebugStream.println("Successful Feed")
    
    
    async def turbo_input(self, coro, rate, terminator: asyncio.Event):
        delay = rate[0]
        while(not(terminator.is_set())):
            DebugStream.print(delay,":\n\t")
            await coro()
            await asyncio.sleep(delay)
            if(delay > rate[1]):
                delay *= rate[2]
    
    
    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    async def noop(self, hall_pass: asyncio.Event = None):
        ''' no operation '''
        # DebugStream.println("nooping")
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
        mv_size = 4
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

        try:
            for wiggle in range(num_wiggles):
                for move in moves:
                    for _ in range(2):
                        await asyncio.sleep(0.02)
                        self.blue.mouse.move( *move )
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in shake_cursor()")
            DebugStream.println(str(ce))
        
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

    async def clicker_task(self):
        Cato.imu.single_tap_cfg()
        while True:
            await Cato.imu.wait()
            try:
                DebugStream.println("Click")
                self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
            except ConnectionError as ce:
                DebugStream.println("ConnectionError: connection lost in clicker_task()")
                DebugStream.println(str(ce))

    async def quick_calibrate(self, hall_pass: asyncio.Event = None):
        await asyncio.sleep(0.5)
        await asyncio.create_task(Cato.imu.calibrate(100))
        await asyncio.create_task(self.shake_cursor())
        hall_pass.set()

    async def quick_sleep(self, hall_pass: asyncio.Event = None):
        Events.sleep.set()
        hall_pass.set()


    async def move_mouse(self, max_idle_cycles=80, mouse_type = "ACCEL", forever: bool = False):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''
        # mem("move_mouse -- pre settings load")
        
        cfg = config['mouse']

        idle_thresh = cfg['idle_thresh'] # speed below which is considered idle  
        min_run_cycles = cfg['min_run_cycles']
        
        #scale is "base" for acceleration - do adjustments here
        screen_size = config['screen_size']
        screen_mag = sqrt(screen_size[0] ** 2 + screen_size[1] ** 2)
        screen_scale = screen_mag / sqrt(1920**2 + 1080**2) # default scale to 1920 * 1080 - use diagonal number of pixels as scalar
        scale = 1.0
        usr_scale = cfg['scale'] #user multiplier

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

        # mem("post_cfg") # At this point, between pre and post, we lost only 100bytes

        while True:
            # print(".")
            if not Events.move_mouse.is_set():

                # DebugStream.println("move mouse -- awaiting")
                pass
    
            await Events.move_mouse.wait() # only execute when move_mouse is set
            await Events.gesture_not_collecting.wait()
            await Cato.imu.wait()
            if cycle_count == 0:
                DebugStream.println(f"+ Mouse Live (mem: {gc.mem_free()})")

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
                scale *= screen_scale

            # Begin idle checking -- only after minimum duration
            if(cycle_count >= min_run_cycles and not forever):
                if( mag <= idle_thresh ): # if too slow
                    # if (idle_count == 0): # count time of idle to finish (design util)
                        # print("\tidle detected, count begun")
                    idle_count += 1
                else:
                    # print("\tactivity resumed: idle counter reset")
                    idle_count = 0

                if idle_count >= max_idle_cycles: # if sufficiently idle, clear move_mouse
                    DebugStream.println(f"\t- Mouse Exit (mem: {gc.mem_free()})")

                    Events.move_mouse.clear()
                    Events.mouse_done.set()

                    idle_count = 0
                    cycle_count = 0

            mag = mag * usr_scale
            # trig scaling of mouse x and y values
            dx = int( scale * mag * cos(ang) )
            dy = int( scale * mag * sin(ang) )

            try:
                self.blue.mouse.move(dx, dy, dscroll)
            except ConnectionError as ce:
                DebugStream.println("ConnectionError: connection lost in move_mouse()")
                DebugStream.println(str(ce))
            
    async def _scroll(self, hall_pass: asyncio.Event = None):
        DebugStream.println("+ _scroll")
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        hall_pass.set()
        DebugStream.println("- _scroll")

    async def scroll(self, hall_pass: asyncio.Event = None):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        
        z = 0.0 #value to integrate to manage scroll
        dt = 1.0 / self.specs["freq"]
        scale = 1.0 # slow down kids

        num_cycles = 0
        while True:
            await Events.scroll.wait() # block if not set
            if num_cycles == 0:
                DebugStream.println("+ Scroll Running")
            num_cycles += 1

            slow_down = 10 # only scroll one line every N cycles
            for i in range(slow_down):
                await Cato.imu.wait()
            
            z += (-1) * scale * self.gz * dt

            try:
                self.blue.mouse.move(0, 0, int(z))
            except ConnectionError as ce:
                DebugStream.println("ConnectionError: connection lost in scroll()")
                DebugStream.println(str(ce))

            if( abs(self.gy) > 30.0 ):
                DebugStream.println("\t- Scroll Broken")
                num_cycles = 0

                z = 0.0
                Events.scroll_done.set()
                Events.scroll.clear()
                if hall_pass is not None:
                    print("\tSCROLL: Scroll_done set & hall_pass set")
                    hall_pass.set()
    
    async def _scroll_lr(self, hall_pass: asyncio.Event = None):
        # Left/Right Scroll Manager
        # Holds Shift, Sets Scroll, Releases Shift.
        print(f"+ _scroll_lr")
        self.blue.k.press(Keycode.LEFT_SHIFT)
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        self.blue.k.release(Keycode.LEFT_SHIFT)
        print(f"b: {gc.mem_free()}")
        if hall_pass is not None:
            DebugStream.println("\t- _scroll_lr")
            hall_pass.set()

    async def left_click(self, hall_pass: asyncio.Event = None): # "Does the send a wait for acknowledgement"
        # determine if async or not
        # can have BLE writes w/wo ack -- send and pray vs confirm
        # time the routine uS ok, mS bad
        ''' docstring stub '''
        try:
            self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in left_click()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def double_click(self, hall_pass: asyncio.Event = None):
        try:
            self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
            self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in double_click()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()


    async def right_click(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.click(self.blue.mouse.RIGHT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in right_click()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def middle_click(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.click(self.blue.mouse.MIDDLE_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in middle_click()")
            DebugStream.println(str(ce))
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
        try:
            self.blue.mouse.press(self.blue.mouse.LEFT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in left_press()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def left_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.release(self.blue.mouse.LEFT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in left_release()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def right_press(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.press(self.blue.mouse.RIGHT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in right_press()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def right_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.release(self.blue.mouse.RIGHT_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in right_release()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def middle_press(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.press(self.blue.mouse.MIDDLE_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in middle_press()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def middle_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.release(self.blue.mouse.MIDDLE_BUTTON)
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in middle_release()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()

    async def all_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.release_all()
        except ConnectionError as ce:
            DebugStream.println("ConnectionError: connection lost in all_release()")
            DebugStream.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()
        
    # cato keyboard actions
    async def press_enter(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("ENTER") 
        #self.blue.k.press(Keycode.ENTER)
        self.blue.k.release(Keycode.ENTER)
        if hall_pass is not None:
            hall_pass.set()
    
    async def press_esc(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("ESC pressed")
        #self.blue.k.press(Keycode.ESCAPE)
        self.blue.k.release(Keycode.ESCAPE)
        if hall_pass is not None:
            hall_pass.set()

    async def press_meta(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("META pressed")
        self.blue.k.press(Keycode.GUI)
        self.blue.k.release(Keycode.GUI)
        if hall_pass is not None:
            hall_pass.set()
    
    async def press_up(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("UP pressed")
        self.blue.k.press(Keycode.UP_ARROW)
        self.blue.k.release(Keycode.UP_ARROW)
        if hall_pass is not None:
            hall_pass.set()
    
    async def press_down(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("DOWN pressed")
        self.blue.k.press(Keycode.DOWN_ARROW)
        self.blue.k.release(Keycode.DOWN_ARROW)
        if hall_pass is not None:
            hall_pass.set()
    
    async def press_left(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("LEFT pressed")
        self.blue.k.press(Keycode.LEFT_ARROW)
        self.blue.k.release(Keycode.LEFT_ARROW)
        if hall_pass is not None:
            hall_pass.set()
    
    async def press_right(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        DebugStream.println("RIGHT pressed")
        self.blue.k.press(Keycode.RIGHT_ARROW)
        self.blue.k.release(Keycode.RIGHT_ARROW)
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

    async def wait_for_motion(self, thresh = 150, *, num = -1):
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
            Events.sig_motion.clear()
            # DebugStream.println("+ Wait_for_motion triggered")
            # DebugStream.println("B: ", gc.mem_free())
            await Cato.imu.wait()
            # DebugStream.println("C: ", gc.mem_free())
            cycles += 1

            val = self.gx ** 2 + self.gy ** 2 + self.gz ** 2

            # BREAK CONDN 1: SIGNIFICANT MOTION
            if val > thresh:
                Events.wait_for_motion.clear()
                Events.sig_motion.set()
            # if cycles > 60*104:
            #     Events.sleep.set()
            #     await asyncio.sleep(0)
                Events.sleep.clear()
            #Break CONDN 2: TIMEOUT
            if num != -1:
                if cycles > num:
                    Events.wait_for_motion.clear()
                    Events.sig_motion.clear()
            # print("D: ", gc.mem_free())
            # exiting cleanup
            if not Events.wait_for_motion.is_set():
                exit_reason = "MOTION" if Events.sig_motion.is_set() else "TIMEOUT"
                # DebugStream.println( f"WAIT FOR MOTION: EXIT : { exit_reason }" )
                Events.wait_for_motion_done.set()
                cycles = 0
            # DebugStream.println("E: ", gc.mem_free())
            # DebugStream.println("")
    
    async def collect_gestures_app():
        from StrUUIDService import SUS
        SUS.collGestUUID = "AWAITING INTERACTION"
        Events.gesture_not_collecting.set()
        while(True):
            if(SUS.collGestUUID[:2] == "CG"):
                Events.gesture_collecting.set()
                Events.gesture_not_collecting.clear()
                DebugStream.println("Collecting Gesture (app)")
                #try:
                gestID : int
                gestLength = config["gesture_length"]
                timeLimit = 3
                args = SUS.collGestUUID[2:].split(',')
                if(len(args) > 3):
                    raise Exception("Too many input args (expects 1-3 ints)")
                gestID = int(args[0])
                if(gestID < 0)or(gestID >= len(EV.gesture_key)):
                    raise Exception("Gesture ID "+gestID+" does not exist")
                
                if(len(args) >= 2):
                    gestLength = int(args[1])
                if(len(args) == 3):
                    timeLimit = int(args[2])
                del(args)
                

                hist = []
                maxGest = []
                maxMag = 0
                drift : tuple

                DebugStream.println("Recording")

                while(len(hist) < gestLength):
                    await Cato.imu.wait()
                    hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))

                drift = hist[gestLength-1]
                maxGest = hist.copy()
                maxMag = maxGest[int(gestLength/2)]
                DebugStream.println(maxMag)
                for g in maxMag:
                    DebugStream.println(type(g))
                maxMag = (maxMag[3]-drift[3])**2 + (maxMag[4]-drift[4])**2 + (maxMag[5]-drift[5])**2
                sw = asyncio.create_task(Cato.stopwatch(timeLimit))  # Timer starts here
                DebugStream.println("Perform Gesture: ", EV.gesture_key[gestID],"(",str(gestID),")")
                
                while(not sw.done()):
                    await Cato.imu.wait()
                    hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
                    hist.pop(0)

                    currMid = hist[int(gestLength/2)]
                    currMag = (currMid[3]-drift[3])**2 + (currMid[4]-drift[4])**2 + (currMid[5]-drift[5])**2
                    if(currMag > maxMag):
                        DebugStream.println("New Max Read")
                        DebugStream.println(currMag, ">", maxMag)
                        maxMag = currMag
                        maxGest = hist.copy()

                DebugStream.println("Gesture Recording Completed")

                while(len(maxGest) > 0):
                    d = maxGest.pop(0)
                    SUS.collGestUUID = ','.join(str(v) for v in d)
                    await asyncio.sleep(0)  ##prob dont need sleep but leaving in for safety

                # except Exception as ex:
                #     SUS.collGestUUID = "EX: "+str(ex)
                #     DebugStream.println(ex)
                
                Events.gesture_collecting.clear()
                Events.gesture_not_collecting.set()
            else:
                await asyncio.sleep(0.1)



    async def stopwatch(n : float,ev : asyncio.Event = None):
        if(n >= 0):
            await asyncio.sleep(n)
            if(ev is not None):
                ev.set()
    
    def shuffle(l : list):
        from random import randint
        for i in range(0,len(l)):
            r = randint(i,len(l)-1)
            if(i != r):
                l[i],l[r] = l[r],l[i]
        return

    async def test_loop(self):
        DebugStream.println("+ test_loop")
        from StrUUIDService import SUS
        SUS.collGestUUID = "test_loop"
        #await self.blue.is_connected.wait()
        i = 0
        t = asyncio.create_task(Cato.stopwatch(10))

        while(True):
            DebugStream.println("looping")

            #DebugStream.println("loop: ",i)
            #DebugStream.println(t.done())
            i += 1
            await asyncio.sleep(10)