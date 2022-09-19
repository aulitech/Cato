'''
Cato.py
auli.tech software to drive the Cato gesture Mouse
Written by Finn Biggs finn@auli.tech
    15-Sept-22
'''

import board
import busio
import time
import digitalio

from adafruit_lsm6ds.lsm6ds3trc import LSM6DS3TRC

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from BluetoothControl import BluetoothControl
from math import sqrt, atan2, sin, cos, pow

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

class Cato:
    ''' Main Class of Cato Gesture Mouse '''
    # SETUP METHODS
    def __init__(self):
        self.gx_trim, self.gy_trim, self.gz_trim = 0, 0, 0
        self.sensor, \
        self.gx,        self.gy,        self.gz,        \
        self.ax,        self.ay,        self.az         \
                = self._setup_imu()
        self.gx_trim, self.gy_trim, self.gz_trim = self.calibrate()
        self.blue = BluetoothControl()
        self.blue.connect_bluetooth()
        self.state = ST.IDLE
        self.st_matrix = [
            #       ST.IDLE             ST.MOUSE_BUTTONS        ST.KEYBOARD
                [   self.noop,          self.noop,              self.noop],     #EV.NONE
                [   self,          self.noop,              self.noop],     #EV.UP
                [   self.noop,          self.noop,              self.noop],     #EV.DOWN
                [   self.noop,          self.noop,              self.noop],     #EV.RIGHT
                [   self.noop,          self.noop,              self.noop],     #EV.LEFT
                [   self.noop,          self.noop,              self.noop],     #EV.ROLL_R
                [   self.noop,          self.noop,              self.noop],     #EV.ROLL_L
                [   self.noop,          self.noop,              self.noop],     #EV.SHAKE_YES
                [   self.noop,          self.noop,              self.noop]      #EV.SHAKE_NO
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

        gx, gy, gz = sensor.gyro
        ax, ay, az = sensor.acceleration
        print("    Done")
        return sensor, gx, gy, gz, ax, ay, az

    def calibrate(self):
        print("Calibrating")
        num_to_calibrate = 1000
        x, y, z = 0, 0, 0
        for cycles in range(num_to_calibrate):
            time.sleep(0.001)
            if(cycles % 100 == 0):
                #print(int(cycles / 10), '%')
                pass
            self.read_imu()
            x += self.gx
            y += self.gy
            z += self.gz
        x = x / num_to_calibrate
        y = y / num_to_calibrate
        z = z / num_to_calibrate
        print("    Done")
        return x, y, z

    # State Control / Execution Utils
    def detect_event(self):
        ''' calls to gesture detection libraries, controls flow of program '''
        return EV.NONE
    def dispatch_event(self, event):
        ''' sends event from detect_event to the state transition matrix '''
        self.st_matrix[event][self.state]()

    # Sensor utils read_IMU, calibrate

    def read_imu(self):
        ''' reads data off of the IMU into -> gx, gy, gz, ax, ay, az '''
        self.gx, self.gy, self.gz = self.sensor.gyro
        rad_to_deg = 57.3 # 360 / 2PI

        self.gx = self.gx*rad_to_deg
        self.gy = self.gy*rad_to_deg
        self.gz = self.gz*rad_to_deg

        self.gx -= self.gx_trim
        self.gy -= self.gy_trim
        self.gz -= self.gz_trim

        self.ax, self.ay, self.az = self.sensor.acceleration

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

    def move_mouse(self):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''
        t_start = time.monotonic()
        idle_count = 0
        idle_thresh = 5.0
        sleep_time = 0.002 #per cycle seconds to delay
        idle_time = 0.5 #seconds to idle before exiting
        max_idle_cycles = 150
        min_run_cycles = 300
        cycle_count = 0
        MOUSE_TYPE = "ACCEL"
        slow_thresh = 20.0
        fast_thresh = 240.0
        scale = 1.0 #remain at 1.0 for linear
        slow_scale = 0.05
        fast_scale = 3.0
        t_idle_start = time.monotonic()
        while(idle_count < max_idle_cycles):
            cycle_count += 1
            #time.sleep(sleep_time)
            self.read_imu()
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
            if( cycle_count == min_run_cycles):
                print("    minimum duration reached at {a} seconds".format( a = (time.monotonic() - t_start) ) )
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
        print( "    Time idled: {} s".format( time.monotonic() - t_idle_start) )

    def scroll(self):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        print("Scrolling")
        multiplier = 0.1
        while(True):
            time.sleep(0.100)
            self.read_imu()
            self.blue.mouse.move(0, 0, int(multiplier * self.gz))
            if(self.gy > 30.0):
                break

    #shift + scroll = lateral scroll on MOST applications
    def scroll_lr(self):
        ''' shift + scroll = lateral scroll on MOST applications
            laterally scroll until exit condition
        '''
        #press shift
        ''' scrolls the mouse until sufficient exit condition is reached '''
        self.blue.k.press(Keycode.SHIFT)
        print("Scrolling")
        multiplier = -0.1
        while(True):
            time.sleep(0.100)
            self.read_imu()
            self.blue.mouse.move(0, 0, int(multiplier * self.gy))
            if(self.gz > 30.0):
                self.blue.k.release(Keycode.SHIFT)
                break
        #release shift

    def left_click(self):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)

    def right_click(self):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.RIGHT_BUTTON)

    def middle_click(self):
        ''' docstring stub '''
        self.blue.mouse.click(self.blue.mouse.MIDDLE_BUTTON)

    def left_click_drag(self):
        ''' docstring stub '''
        print("Left click")
        self.left_press()
        print("Drag")
        self.move_mouse()
        self.left_release()
        print("Mouse released")

    def right_click_drag(self):
        ''' docstring stub '''
        self.right_press()
        self.move_mouse()
        self.right_release()

    def middle_click_drag(self):
        ''' docstring stub '''
        self.middle_press()
        self.move_mouse()
        self.middle_release()

    def left_press(self):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.LEFT_BUTTON)

    def left_release(self):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.LEFT_BUTTON)

    def right_press(self):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.RIGHT_BUTTON)

    def right_release(self):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.RIGHT_BUTTON)

    def middle_press(self):
        ''' docstring stub '''
        self.blue.mouse.press(self.blue.mouse.MIDDLE_BUTTON)

    def middle_release(self):
        ''' docstring stub '''
        self.blue.mouse.release(self.blue.mouse.MIDDLE_BUTTON)

    def all_release(self):
        ''' docstring stub '''
        self.blue.mouse.release_all()

    # cato keyboard actions
    def press_enter(self):
        ''' docstring stub '''
        self.blue.k.press(Keycode.ENTER)
        self.blue.k.release(Keycode.ENTER)

    # ToDo, the rest of the keyboard buttons