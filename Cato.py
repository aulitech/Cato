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


neuton_outputs = array.array( "f", [0, 0, 0, 0, 0, 0, 0, 0] )

def mem():
    print(f"MEM FREE: {gc.mem_free()}")
    gc.collect()
    print(f"MEM FREE: {gc.mem_free()}")

class Cato:
    ''' Main Class of Cato Gesture Mouse '''
    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        print("Cato init: start")

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
        self.specs["num_samples"] = 3

        # battery managing container
        self.battery = battery.Bat()


        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        self.blue = BluetoothControl.BluetoothControl()
        
        self.state = ST.IDLE

        # Set up state matrix control
        self.st_matrix = []
        for row in self.config['st_matrix']:
            tmp_row = []
            for entry in row:
                cmd = f"self.{entry}"
                tmp_row.append( eval(cmd, {"self":self}) )
            self.st_matrix.append(tmp_row)
        print(self.st_matrix)
        self.gx_trim, self.gy_trim, self.gz_trim = 0, 0, 0

        self.events = Events

        self.imu = LSM6DS3TRC()

        print("mc.nvm[0] = ",mc.nvm[0]," ")
        if(self.config["operation_mode"] >=20)&(bool(mc.nvm[0])):  ###prob want to replace >=20 w more robust boolDict of selfwrite modes
            print("BOOTING SELF-WRITABLE")
            mc.nvm[0] = 0       #switch bit to boot board self writable
            print("mc.nvm[0] = ",bool(mc.nvm[0])," ")
            time.sleep(1)       ##this is here just so print statements finish
            mc.reset()
        print("-- past writable check")

        # blocking functions enabled by events
        if(self.config["operation_mode"] == 0):
            self.tasks = {
                "wait_for_motion"   : self.wait_for_motion(),
                "move_mouse"        : self.move_mouse(),
                "detect_event"      : self.detect_event(),
                "scroll"            : self.scroll()
            }
        elif(self.config["operation_mode"] >=20):
            self.tasks = {
                "wait_for_motion"   : self.wait_for_motion(),
                "collect_gestures"  : self.collect_gestures()
                #"scroll"            : self.scroll()
            }
        self.tasks.update(self.imu.tasks)
        self.tasks.update(self.blue.tasks)
        
        self.n = Neuton(outputs=neuton_outputs)
        self.gesture = EV.NONE

        print("Cato init -- finish")

    # def display_gesture_menu(self):
    #     print("Available actions: ")
    #     for ev in range(len(self.st_matrix)):
    #         print("\tevent: {}\n\t\taction: {}".format(ev, self.st_matrix[ev][self.state].__name__))

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

    async def _move_mouse(self, hall_pass: asyncio.Event = None):
        print("_move_mouse -- top")
        self.events.move_mouse.set()
        await self.events.mouse_done.wait()
        self.events.mouse_done.clear()
        hall_pass.set()
        print("_move_mouse -- finish")
    
    async def block_on(self, coro):
        '''
            await target function having uncertain runtime which also needs to use async imu functionality  \n
            coro: Coroutine or other awaitable
        '''
        await coro(self.hall_pass)
        await self.hall_pass.wait()
        self.hall_pass.clear()
    
    async def detect_event(self): 
        ''' calls to gesture detection libraries '''
        gesture = EV.NONE
        while True:
            await self.events.detect_event.wait()
            self.events.detect_event.clear()

            await self.imu.wait()
            print("Shaking Cursor")
            await self.shake_cursor()
            print("Done shaking cursor")
            print("Block on wait for motion")
            await self.block_on(self._wait_for_motion)
            print("finished wait ")

            # RUNS OUT OF MEM HERE

            print('RIGHT BEFORE NEUTON')
            print(gc.mem_free() )
            gc.collect()
            print(gc.mem_free() )
            motion_detected = self.events.sig_motion.is_set()
            
            if motion_detected:
                self.events.sig_motion.clear()

                neuton_needs_more_data = True
                arr = array.array( 'f', [0]*6 )
                
                i = 1 #buf pos tracker
                while( neuton_needs_more_data ):
                    await self.imu.wait()
                    arr[0] = self.ax
                    arr[1] = self.ay
                    arr[2] = self.az
                    arr[3] = self.gx
                    arr[4] = self.gy
                    arr[5] = self.gz
                    neuton_needs_more_data = self.n.set_inputs( arr )
                    i += 1

                
                print(f"post buffer fill")
                mem()
                gesture = self.n.inference() + 1 # plus one ensures that 0 event is "none"
                confidence = max(neuton_outputs)

                confidence_thresh = 0.80
                if confidence < confidence_thresh:
                    gesture = EV.NONE

            else:
                # print("D_EV: wait_for_motion timed out")
                gesture = EV.NONE
            
            print("detect_event pre function call")
            mem()

            target_fn = self.st_matrix[gesture][self.state]
            print(f"target_fn: {target_fn.__name__}")

            await self.block_on(target_fn)
            print("detect_event post fn call")
            mem()

            self.events.control_loop.set()

    
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
        mv_size = 10
        num_wiggles = 1
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
                await self.imu.wait()
                await self.imu.wait()
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
        idle_thresh = self.config['mouse']['idle_thresh'] # speed below which is considered idle  
        min_run_cycles = self.config['mouse']['min_run_cycles']
        
        #scale is "base" for acceleration - do adjustments here
        scale = 1.0
        usr_scale = self.config['mouse']['scale'] #user multiplier

        """ TODO: have these values arise out of config """
        # dps limits for slow vs mid vs fast movement        
        slow_thresh = self.config['mouse']['slow_thresh']
        fast_thresh = self.config['mouse']['fast_thresh']

        # scale amount for slow and fast movement, mid is linear translation between
        slow_scale = self.config['mouse']['slow_scale']
        fast_scale = self.config['mouse']['fast_scale']

        # number of cycles currently idled (reset to 0 on motion)
        idle_count = 0

        # number of cycles run in total
        cycle_count = 0
        dx = 0
        dy = 0
        dscroll = 0
        while True:
            # print(".")
            if not self.events.move_mouse.is_set():
                print("move mouse -- awaiting")
            await self.events.move_mouse.wait() # only execute when move_mouse is set
            
            await self.imu.wait()
            
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
                pass

            # mouse with dynamic acceleration for fine and coarse control
            if(mouse_type == "ACCEL"):
                scale = Cato.translate(slow_thresh, fast_thresh, slow_scale, fast_scale, mag)

            # Begin idle checking -- only after minimum duration
            if(cycle_count >= min_run_cycles ):

                if( mag <= idle_thresh ): # if too slow
                    # if (idle_count == 0): # count time of idle to finish (design util)
                        # print("\tidle detected, count begun")
                    idle_count += 1
                else:
                    # print("\tactivity resumed: idle counter reset")
                    idle_count = 0

                if idle_count >= max_idle_cycles: # if sufficiently idle, clear move_mouse
                    # print(f"Idle cycles: {idle_count}")
                    # print(f"Idle limit: {max_idle_cycles}")
                    print("\tMouse Exit")
                    self.events.move_mouse.clear()
                    self.events.mouse_done.set()
                    idle_count = 0
                    cycle_count = 0
                    # print(f"post-reset cycle count: {cycle_count}")
            
            mag = mag * usr_scale
            # trig scaling of mouse x and y values
            dx = int( scale * mag * cos(ang) )
            dy = int( scale * mag * sin(ang) )
            # print(dx, dy, dscroll, sep = ', ')
            # print( dir(self.blue.mouse.move) )
            self.blue.mouse.move(dx, dy, dscroll)

        #print( "    Time idled: {} s".format( time.monotonic() - t_idle_start) )

    async def _scroll(self, hall_pass: asyncio.Event = None):
        self.events.scroll.set()
        await self.events.scroll_done.wait()
        self.events.scroll_done.clear()
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
                await self.imu.wait()
            
            z += (-1) * scale * self.gz * dt

            # print(f"z: {z}")
            # print( id(self.blue.mouse) )
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
        self.events.scroll.set()
        await self.events.scroll_done.wait()
        self.events.scroll_done.clear()
        self.blue.k.release(Keycode.LEFT_SHIFT)

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

    @property
    def o_str(self):
        return "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f}".format(self.last_read, self.ax, self.ay, self.az, self.gx, self.gy, self.gz)

    async def _wait_for_motion(self, hall_pass: asyncio.Event = None):
        self.events.wait_for_motion_done.clear()
        self.events.wait_for_motion.set()
        print("_ WAIT FOR MOTION: WAITING")
        await self.events.wait_for_motion_done.wait()
        self.events.wait_for_motion_done.clear()
        hall_pass.set()

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
            # print("wait_for_motion triggered")
            await self.imu.wait()

            cycles += 1

            val = self.gx ** 2 + self.gy ** 2 + self.gz ** 2
            
            # BREAK CONDN 1: SIGNIFICANT MOTION
            if val > thresh:
                self.events.wait_for_motion.clear()
                self.events.sig_motion.set()
            
            #Break CONDN 2: TIMEOUT
            if num != -1:
                if cycles > num:
                    self.events.wait_for_motion.clear()
                    self.events.sig_motion.clear()

            # exiting cleanup
            if not self.events.wait_for_motion.is_set():
                exit_reason = "MOTION" if self.events.sig_motion.is_set() else "TIMEOUT" 
                print( f"WAIT FOR MOTION: EXIT : { exit_reason }" )
                self.events.wait_for_motion_done.set()
                cycles = 0

                if hall_pass is not None:
                    hall_pass.set()


    async def collect_gestures(self, logName = "log.txt", n = 2, winSize = 76):
        await self.blue.is_connected.wait()
        await self.events.collect_gestures.wait()
        print("Collecting Gestures")
        gest_timer = asyncio.Event()
        for gestID in range(5):
            while(n > 0):
                
                n -= 1
                hist = []
                maxGest = list
                maxAbs = float

                # gather data from imu for 5sec
                c = 0
                start = 0
                counter = int
                with open("collgest_event_log.txt",'w') as evLog:
                    evLog.write("Reading Data")
                    while(not gest_timer.is_set()):#|(time.time()-start < 2):
                        await self.imu.wait()
                        hist.append((self.ax, self.ay, self.az, self.gx, self.gy, self.gz, gestID))
                        # if(c == 0):
                        #     print(",\t".join(str(v) for v in hist[len(hist)-1]))
                        # c = (c+1)%32

                        if(len(hist) == winSize):
                            maxGest = hist.copy()
                            maxAbs = maxGest[int(winSize/2)]
                            maxAbs = maxAbs[0]**2 + maxAbs[1]**2+maxAbs[2]**2
                            self.bluType("Perform Gesture "+str(gestID))
                            print("Perform Gesture: ",gestID)
                            evLog.write("Timer Started")
                            asyncio.create_task(self.countN(gest_timer, 5))  # Timer starts here
                            start = time.time()
                            counter = -1
                        
                        ##could check max acc as it's read to cut mem by 1/4 (would require splitting maxGest into pre/post queues)
                        elif(len(hist) > winSize):
                            hist.pop(0)
                            currMid = hist[int(winSize/2)]                    
                            currAbs = currMid[3]**2 + currMid[4]**2 + currMid[5]**2
                            if(currAbs > maxAbs):
                                evLog.write("New Max Read")
                                maxAbs = currAbs
                                maxGest = hist.copy()

                            # if(counter < round(time.time() -start)):
                            #     counter = round(time.time()-start)
                            #     print(counter,": ",time.time()-start)
                    gest_timer.clear()
                    self.bluType("Gesture Collected")
                    self.bluType("Logging Max")
                    evLog.write("Logging Max")
                    
                # record data
                with open(logName,"w") as log:       ##swap to append for final?
                    print("Writing to",logName)
                    while(len(maxGest) > 0):
                        d = maxGest.pop(0)
                        log.write(",".join(str(v) for v in d))
                        log.write("\n")

        print("Gesture Collection Completed")
        self.bluType("Gesture Collection Completed")

        asyncio.create_task(self.countN(gest_timer, 5))
        await gest_timer.wait()
        mc.nvm[0] = True
        #raise Exception("Gesture Collection Completed")
    

    def bluType(self, str):
        print("+ bluType")
        for c in str:
            if(ord(c) >= 97):
                c = ord(c) - 93
            elif(ord(c) >= 65):
                self.blue.k.press(225)  #LShift
                c = ord(c) - 61
            elif(c == ' '):
                c = 44
            elif(c == '0'):
                c = 39
            else:
                c = int(c) + 29
            self.blue.k.press(c)
            self.blue.k.release_all()
        self.blue.k.send(40)    #Enter
        print("- bluType")
            

    
    async def countN(self, ev, n):
        #print("+ countN")
        await asyncio.sleep(n)
        ev.set()