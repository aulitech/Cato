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

from imu import LSM6DS3TRC

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from math import sqrt, atan2, sin, cos, pow
import array
import supervisor as sp
import battery

import asyncio

from neutonml import Neuton


#helpers and enums

class ST():
    '''enum states'''
    IDLE = 0
    MOUSE_BUTTONS = 1
    KEYBOARD = 2


class EV():
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

class Spec:
    ''' Specifications '''
    freq = 100 
    imu_ms_delay = 1000.0 / freq
    g_dur = 0.75 # gesture duration (seconds)
    num_samples = int(freq * g_dur)

neuton_outputs = array.array( "f", [0, 0, 0, 0, 0, 0, 0, 0] )

class Cato:
    ''' Main Class of Cato Gesture Mouse '''
    # SETUP METHODS
    def __init__(self, bt = True):

        try:    
            with open("config.json", 'r') as f:
                self.config = json.load(f)
        except:
            mc.reset()


        #enumerate events
        self.events = {
            "imu"               : asyncio.Event(),
            "move_mouse"        : asyncio.Event(),
            "scroll"            : asyncio.Event(),
            "hang_until_motion" : asyncio.Event()
        }


        self.gx_trim, self.gy_trim, self.gz_trim = 0, 0, 0
        self.last_read = sp.ticks_ms()

        self.buf = 0

        self.battery = battery.Bat()

        (   self.sensor, 
            self.time_hist,
            self.gx_hist,        self.gy_hist,        self.gz_hist,     
            self.ax_hist,        self.ay_hist,        self.az_hist         
        )   = self._setup_imu() 

        self.gx_trim, self.gy_trim, self.gz_trim = asyncio.run( self.calibrate() )

        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        
        self.blue = BluetoothControl.BluetoothControl()
        self.blue.connect_bluetooth()
        
        self.state = ST.IDLE
        self.st_matrix = [
            #       ST.IDLE                     ST.MOUSE_BUTTONS            ST.KEYBOARD
                [   self.move_mouse,            self.to_idle,               self.to_idle        ], #EV.UP           = 0
                [   self.left_click,            self.left_click,            self.press_enter    ], #EV.DOWN         = 1
                [   self.scroll,                self.noop,                  self.noop           ], #EV.RIGHT        = 2
                [   self.hang_until_motion,     self.noop,                  self.noop           ], #EV.LEFT         = 3
                [   self.scroll_lr,             self.noop,                  self.noop           ], #EV.ROLL_R       = 4
                [   self.scroll_lr,             self.noop,                  self.noop           ], #EV.ROLL_L       = 5
                [   self.double_click,          self.noop,                  self.noop           ], #EV.SHAKE_YES    = 6
                [   self.hang_until_motion,     self.noop,                  self.noop           ], #EV.SHAKE_NO     = 7
                [   self.noop,                  self.noop,                  self.noop           ]  #EV.NONE         = 8
        ]

        self.n = Neuton(outputs=neuton_outputs)
        
        self.tasks = [
            asyncio.create_task( self.stream_imu() ),
            asyncio.create_task( self.read_imu() )
        ]

    def _setup_imu(self):
        ''' helper method -- encapsulate imu portion of init '''
        print("IMU setup")
        imupwr = digitalio.DigitalInOut(board.IMU_PWR)
        imupwr.direction = digitalio.Direction.OUTPUT
        imupwr.value = True
        time.sleep(0.1)
        imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        sensor = LSM6DS3TRC(imu_i2c)

        gx = [0]*Spec.num_samples
        gy = [0]*Spec.num_samples
        gz = [0]*Spec.num_samples
        ax = [0]*Spec.num_samples
        ay = [0]*Spec.num_samples
        az = [0]*Spec.num_samples

        time_hist = [0]*Spec.num_samples

        gx[self.buf], gy[self.buf], gz[self.buf] = sensor.gyro
        ax[self.buf], ay[self.buf], az[self.buf] = sensor.acceleration
        
        self.buf = (self.buf + 1) % Spec.num_samples
        print("    Done")
        return sensor, time_hist, gx, gy, gz, ax, ay, az

    async def stream_imu(self):
        ''' filler method to stream raw data from the imu '''
        while True:
            self.events["imu"].set()
            await asyncio.sleep(0.001)
            print( f"{self.gx}, {self.gy}, {self.gz}" )

    async def calibrate(self):
        print("Calibrating")
        num_to_calibrate = 200
        x, y, z = 0, 0, 0
        for cycles in range(num_to_calibrate):
            self.events["imu"].set()
            x += self.gx
            y += self.gy
            z += self.gz
        x = x / num_to_calibrate
        y = y / num_to_calibrate
        z = z / num_to_calibrate
        print("    Done")
        return x, y, z

    def display_gesture_menu(self):
        print("Available actions: ")
        for ev in range(len(self.st_matrix)):
            print("\tevent: {}\n\t\taction: {}".format(ev, self.st_matrix[ev][self.state].__name__))

    # State Control / Execution Utils
    async def detect_event(self):
        ''' calls to gesture detection libraries, controls flow of program '''
        #self.display_gesture_menu()
        print("\nDetecting Event")
        if await self.hang_until_motion(loop_after = 4 * Spec.num_samples):
            print("Motion!")
            pass
        else:
            print("Waited and got no motion")
            return
        await self.read_gesture()
        print("Finished Reading Gesture")
        flag = True
        i = 1
        arr = array.array( 'f', [0]*6)
        print("pre-read")
        while(True):
            # await asyncio.sleep(0.001)
            b_pos = (i + self.buf) % Spec.num_samples
            arr[0] = self.ax_hist[b_pos]
            arr[1] = self.ay_hist[b_pos]
            arr[2] = self.az_hist[b_pos]
            arr[3] = self.gx_hist[b_pos]
            arr[4] = self.gy_hist[b_pos]
            arr[5] = self.gz_hist[b_pos]

            #self.garbage = array.array('f', [0]*1000)
            flag = self.n.set_inputs( arr )
            #self.garbage = array.array('f', [0]*1000)
            i += 1
            if bool(flag) == False:
                break
        print("pre-inference")
        inf = self.n.inference()
        print("post-inference")
        confidence = max(neuton_outputs)
        print( f"Diagnosis: {inf}, {dir(inf)}" )
        # print("\tMax Confidence:  {}".format(confidence))
        # print("\tPredicted Index: {}".format(inf))
        # print("\tOutputs:         {}".format(outputs))
        confidence_thresh = 0.80
        ret_val = inf
        if confidence < confidence_thresh:
            ret_val = 8
        return ret_val

    async def dispatch_event(self, event):

        ''' sends event from detect_event to the state transition matrix '''
        print("Dispatch Event Called with event = {}".format(event))
        print("event: {}, state: {}".format(event, self.state))
        print(self.st_matrix[event][self.state].__name__)
        try:
            await self.st_matrix[event][self.state]()
        except AttributeError:
            self.st_matrix[event][self.state]()
    
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

    async def read_imu(self):
        ''' reads data off of the IMU into -> gx, gy, gz, ax, ay, az '''
        while True:
            await self.events["imu"].wait()
            self.buf = (self.buf + 1) % Spec.num_samples
            dt = (sp.ticks_ms() - self.last_read) % 2**29 #ticks_ms overflow amount
            print("dt = {}".format(dt))
            if(dt < Spec.imu_ms_delay):
                await asyncio.sleep((Spec.imu_ms_delay - dt) / 1000)
            
            self.last_read = sp.ticks_ms()
            self.time_hist[self.buf] = self.last_read
            
            rad_to_deg = 57.3 # 360 / 2PI
            self.gx_hist[self.buf], self.gy_hist[self.buf], self.gz_hist[self.buf] = [(x * rad_to_deg) for x in self.sensor.gyro]
            self.ax_hist[self.buf], self.ay_hist[self.buf], self.az_hist[self.buf] = self.sensor.acceleration
            
            self.gx_hist[self.buf] -= self.gx_trim
            self.gy_hist[self.buf] -= self.gy_trim
            self.gz_hist[self.buf] -= self.gz_trim
            
            self.events["imu"].clear()

            # print( sp.ticks_ms() )
            #self.print_o_str()

    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    def noop(self):
        ''' no operation '''
        print("nooping")
    
    def to_idle(self):
        self.state = ST.IDLE
    
    def to_mouse_buttons(self):
        self.state = ST.MOUSE_BUTTONS
    
    def to_keyboard(self):
        self.state = ST.KEYBOARD
        
    # Cato Mouse Actions
    async def shake_cursor(self):
        m = self.blue.mouse
        mv_size = 10
        num_wiggles = 1
        delay = 0.030
        orig_pos = [0, 0]
        moves = [
            (-mv_size,      0,          0),
            (0,             mv_size,    0),
            (2*mv_size,     0,          0),
            (0,             -2*mv_size, 0),
            (-2*mv_size,    0,          0),
            (0,             2*mv_size,  0),
            (mv_size,       -mv_size,   0)
        ]

        for w in range(num_wiggles):
            for move in moves:
                self.blue.mouse.move(*move)
                await asyncio.sleep(delay)

    async def long_pointer(self):
        await self.move_mouse(200)     

    async def move_mouse(self, max_idle_cycles=50):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''
        
        await self.shake_cursor()
        print("\nMOVE MOUSE CALLED")
        t_start = time.monotonic()
        idle_count = 0
        idle_thresh = 5.0
        min_run_cycles = 4 * Spec.g_dur
        cycle_count = 0
        MOUSE_TYPE = "ACCEL"
        slow_thresh = 20.0
        fast_thresh = 240.0

        #scale is "base" for acceleration - do adjustments here
        scale = 1.0 #remain at 1.0 for linear

        slow_scale = 0.2
        fast_scale = 3.0
        t_idle_start = time.monotonic()
        while(idle_count < max_idle_cycles):
            cycle_count += 1
            # time.sleep(sleep_time)
            await self.read_imu()
            x_mvmt = self.gy
            y_mvmt = self.gz
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = atan2(y_mvmt, x_mvmt)
            #print("mag: {mag}, ang: {ang}".format(mag = mag, ang = ang))
            scale_str = "linear"
            #control mouse scale / type
            #print(mag)

            if(MOUSE_TYPE == "LINEAR"):
                scale = 1.0
            if(MOUSE_TYPE == "ACCEL"):
                if(mag <= slow_thresh):
                    #print("s")
                    scale = slow_scale
                elif(mag > slow_thresh and mag <= fast_thresh):
                    #print("m")
                    scale = slow_scale + (fast_scale - slow_scale)/(fast_thresh - slow_thresh)*(mag - slow_thresh)
                else:
                    #print("f")
                    scale = fast_scale
            #idle checking
            # if( cycle_count == min_run_cycles):
            #     print("    minimum duration reached at {a} seconds".format( a = (time.monotonic() - t_start) ) )
            
            if( mag <= idle_thresh and cycle_count >= min_run_cycles): #only count idle if it's after minimum run length
                #print("idle detected ({a}) max idle: {b}".format(a=idle_count, b=max_idle_cycles))
                if (idle_count == 0):
                    t_idle_start = time.monotonic()
                idle_count += 1
            else:
                idle_count = 0
            #print("rate: %s, x: %f, y: %f" % (scale_str, x_amt, y_amt))
            #self.blue.mouse.move(int(self.gy), int(self.gz))
            self.blue.mouse.move(int(scale * mag * cos(ang)), int(scale * mag * sin(ang)), 0)
            await asyncio.sleep(0)
        await self.shake_cursor()
        #print( "    Time idled: {} s".format( time.monotonic() - t_idle_start) )

    async def joystick_move(self):
        await asyncio.sleep(0.1)
        pos = [0, 0] # x, y
        idle_count = 0
        idle_max = 200

        while idle_count < idle_max:
            await self.read_imu()
            await asyncio.sleep(0.001)

            scale = 0.02

            pos[0] += scale * self.gy
            pos[1] += 1.3 * scale * self.gz #1.3 is for extra vertical sensitivity
            
            print(pos)
            #scale value for mouse movement at different levels
            speed = {
                "low" : 0.1,
                "mid" : 0.2,
                "max" : 0.3
            }

            #thresholds defining left(low) edge of movespeed regions
            tr = { 
                
                "low" : 5,
                "mid" : 10,
                "max" : 15
            }
            
            x_scale = 0
            if abs(pos[0]) > tr["max"]:
                x_scale = speed["max"]
            elif tr["mid"] < abs(pos[0]) < tr["max"]:
                x_scale = speed["mid"]
            elif tr["low"] < abs(pos[0]) < tr["mid"]:
                x_scale = speed["low"]
            else:
                pass

            y_scale = 0
            if abs(pos[1]) > tr["max"]:
                y_scale = speed["max"]
            elif tr["mid"] < abs(pos[1]) < tr["max"]:
                y_scale = speed["mid"]
            elif tr["low"] < abs(pos[1]) < tr["mid"]:
                y_scale = speed["low"]
            else:
                pass

            self.blue.mouse.move( int(x_scale * pos[0]), int(y_scale * pos[1]) )

            if ( pos[0] <= tr["low"] and pos[1] <= tr["low"] ):
                idle_count += 1
            else:
                idle_count = 0

    def do_integration(self):
        x = 0
        y = 0
        z = 0
        while(True):
            self.read_imu()
            x += self.gx * Spec.imu_ms_delay / 1000
            y += self.gy * Spec.imu_ms_delay / 1000
            z += self.gz * Spec.imu_ms_delay / 1000
            print("{:5.2f}, {:5.2f}, {:5.2f}".format(x, y, z))
        
    async def scroll(self):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        print("Scrolling")
        x = 0.0
        y = 0.0
        z = 0.0
        multiplier = 0.1
        t_last_scrolled = sp.ticks_ms()
        scroll_interval = 250 # in ms
        interval_multiplier = 1
        while(True):
            await self.read_imu()

            x += self.gx * Spec.imu_ms_delay / 1000
            y += self.gy * Spec.imu_ms_delay / 1000
            z += self.gz * Spec.imu_ms_delay / 1000

            interval_multiplier = 20 / abs(z)
            if abs(z) < 3:
                interval_multiplier = 100000

            if(sp.ticks_ms() - t_last_scrolled >= interval_multiplier * scroll_interval):
                t_last_scrolled = sp.ticks_ms()
                self.blue.mouse.move(0, 0, -1 if z > 0 else 1)

            if(self.gy > 30.0):
                print("\tScroll Broken")
                break

    #shift + scroll = lateral scroll on MOST applications
    async def scroll_lr(self):
        ''' shift + scroll = lateral scroll on MOST applications
            laterally scroll until exit condition
        '''
        print("Scrolling LR")
        #press shift
        ''' scrolls the mouse until sufficient exit condition is reached '''
        print("Press Shift")
        self.blue.k.press(Keycode.SHIFT)
        #self.blue.k.release(Keycode.SHIFT)
        multiplier = -0.1
        while(True):
            await asyncio.sleep(0.100)
            await self.read_imu()
            self.blue.mouse.move(0, 0, int(multiplier * self.gy))
            if(self.gz > 30.0):
                break
        self.blue.k.release(Keycode.SHIFT)
        #release shift

    async def left_click(self):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)

    async def double_click(self):
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)

    async def right_click(self):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.RIGHT_BUTTON)

    async def middle_click(self):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.MIDDLE_BUTTON)

    async def left_click_drag(self):
        ''' docstring stub '''
        print("Left click")
        await self.left_press()
        print("Drag")
        await self.move_mouse()
        await self.left_release()
        print("Mouse released")

    async def right_click_drag(self):
        ''' docstring stub '''
        await self.right_press()
        await self.move_mouse()
        await self.right_release()

    async def middle_click_drag(self):
        ''' docstring stub '''
        await self.middle_press()
        await self.move_mouse()
        await self.middle_release()

    async def left_press(self):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.LEFT_BUTTON)

    async def left_release(self):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.LEFT_BUTTON)

    async def right_press(self):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.RIGHT_BUTTON)

    async def right_release(self):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.RIGHT_BUTTON)

    async def middle_press(self):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.MIDDLE_BUTTON)

    async def middle_release(self):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.MIDDLE_BUTTON)

    async def all_release(self):
        ''' docstring stub '''
        self.blue.mouse.release_all()

    # cato keyboard actions
    async def press_enter(self):
        ''' docstring stub '''
        self.blue.k.press(Keycode.ENTER)
        self.blue.k.release(Keycode.ENTER)

    # ToDo, the rest of the keyboard buttons

    # DATA COLLECTION TASK:
    @property
    def o_str(self):
        return "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f}".format(self.last_read, self.ax, self.ay, self.az, self.gx, self.gy, self.gz)

    def print_o_str(self):
        print(f"{self.o_str}")

    async def hang_until_motion(self, tr = 105, **kwargs):
        """
            tr = threshold of motion to break loop
            kw_args:
                loop_after number of cycles after which to call move mouse
        """
        print("Waiting for Significant Motion")
        x_scale = 1.00
        y_scale = 1.00
        z_scale = 1.85
        thresh = tr

        wait_time = 0
        val = sqrt(x_scale * self.gx**2 + y_scale * self.gy**2 + z_scale * self.gz**2)
        indef_stated = False
        while(val < thresh):
            await asyncio.sleep(0.005)
            if "loop_after" in kwargs:     
                wait_time += 1
                if wait_time > kwargs["loop_after"]:
                    return False
            else:
                if not indef_stated:
                    print("Indefinite wait for motion")
                    indef_stated = True
            await self.read_imu()
            val = sqrt(x_scale * self.gx**2 + y_scale * self.gy**2 + z_scale * self.gz**2)
        return True

            


    async def read_gesture(self):
        await self.read_imu()
        for i in range(Spec.num_samples):
            await self.read_imu()
    
    def collect_n_gestures(self, n=1):
        for file in os.listdir("/data"):
            try:
                print("removing existing copy of {}".format(file))
                os.remove("data/{}".format(file))
            except:
                print("could not remove {}".format(file))
        for i in range(n):
            my_file = "data/data{:02}.txt".format(i)
            print("Ready to read into: {}".format(my_file))
            print("    Waiting for motion")
            self.hang_until_motion()
            print("Capturing")
            self.read_gesture()
            print("Done")
            my_string = ""
            chunks = 0
            chunksize = 10
            with io.open(my_file, "w") as f:
                temp = ""
                print("{} opened".format(my_file))
                for sample in range(Spec.num_samples):
                    b_pos = (self.buf + sample + 1) % Spec.num_samples
                    temp = "%d,%f,%f,%f,%f,%f,%f" % (self.time_hist[b_pos],    
                                                    self.ax_hist[b_pos],    self.ay_hist[b_pos],    self.az_hist[b_pos],
                                                    self.gx_hist[b_pos],    self.gy_hist[b_pos],    self.gz_hist[b_pos])
                    chunks += 1
                    print(temp, file = f)
                    if chunks % chunksize == 0:
                        print('', file=f, flush=True, end='')
                    #f.write("%d,%f,%f,%f,%f,%f,%f\r\n" % (self.time_hist[b_pos],    self.ax_hist[b_pos],    self.ay_hist[b_pos],    self.az_hist[b_pos],  \
                    #                                                            self.gx_hist[b_pos],    self.gy_hist[b_pos],    self.gz_hist[b_pos]) )
                #f.write(my_string)
                #print(my_string)
                f.close()
            print("{} written".format(my_file))