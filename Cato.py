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
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from BluetoothControl import BluetoothControl
from math import sqrt, atan2, sin, cos

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
        self.sensor, \
        self.gx, self.gy, self.gz, \
        self.ax, self.ay, self.az \
                = self._setup_imu()
        self.blue = BluetoothControl()
        self.blue.connect_bluetooth()
        self.state = ST.IDLE
        self.st_matrix = [
            #       ST.IDLE             ST.MOUSE_BUTTONS        ST.KEYBOARD
                [   self.noop,          self.noop,              self.noop],     #EV.NONE
                [   self.noop,          self.noop,              self.noop],     #EV.UP
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
        imupwr = digitalio.DigitalInOut(board.IMU_PWR)
        imupwr.direction = digitalio.Direction.OUTPUT
        imupwr.value = True
        time.sleep(0.1)
        imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        sensor = LSM6DS3TRC(imu_i2c)

        gx, gy, gz = sensor.gyro
        ax, ay, az = sensor.acceleration

        return sensor, gx, gy, gz, ax, ay, az

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
        self.ax, self.ay, self.az = self.sensor.acceleration

    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    def noop(self):
        ''' no operation '''
        print("nooping")
    
    # Cato Mouse Actions

    def move_mouse(self):
        '''
            move the mouse via bluetooth until sufficiently idle
            returns to idle
        '''
        idle_count = 0
        max_idle_cycles = 100
        idle_thresh = 1.0
        #MOUSE_TYPE = "LINEAR"
        MOUSE_TYPE = "ACCEL"
        slow_thresh = 1.8
        fast_thresh = 5.0
        scale = 1.0
        sleep_time = 0.010 #per cycle seconds to delay
        idle_time = 0.5 #seconds to idle before exiting
        max_idle_cycles = int(idle_time / sleep_time)
        while(idle_count < max_idle_cycles):
            time.sleep(sleep_time)
            self.read_imu()
            x_mvmt = 10 * self.gy
            y_mvmt = 10 * self.gz
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = atan2(y_mvmt, x_mvmt)
            #scale_str = "linear"
            #control mouse scale / type
            if(MOUSE_TYPE == "LINEAR"):
                pass
            if(MOUSE_TYPE == "ACCEL"):
                if(mag <= slow_thresh):
                    #scale_str = "slow"
                    scale = mag*1.0
                elif(mag > slow_thresh and mag <= fast_thresh):
                    #scale_str = "mid"
                    scale = mag*2.5
                else:
                    #scale_str = "fast"
                    scale = mag*4.0

            #idle checking
            if( mag <= idle_thresh ):
                #print("idle detected ({a}) max idle: {b}".format(a=idle_count, b=max_idle_cycles))
                idle_count += 1
            else:
                idle_count = 0
            x_amt = scale * cos(ang)
            y_amt = scale * sin(ang)
            #print("rate: %s, x: %f, y: %f" % (scale_str, x_amt, y_amt))
            self.blue.mouse.move(int(x_amt), int(y_amt), 0)

    def scroll(self):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        while (not True):
            scroll_amt = 0
            self.blue.mouse.move(0, 0, scroll_amt)

    #shift + scroll = lateral scroll on MOST applications
    def scroll_lr(self):
        ''' shift + scroll = lateral scroll on MOST applications
            laterally scroll until exit condition
        '''
        #press shift
        scroll_amt = 0
        while(not True):
            self.blue.mouse.move(0, 0, scroll_amt)
        #release shift

    def left_click(self):
        ''' docstring stub '''

    def right_click(self):
        ''' docstring stub '''

    def middle_click(self):
        ''' docstring stub '''

    def left_click_drag(self):
        ''' docstring stub '''

    def right_click_drag(self):
        ''' docstring stub '''

    def left_press(self):
        ''' docstring stub '''

    def left_release(self):
        ''' docstring stub '''

    def right_press(self):
        ''' docstring stub '''

    def right_release(self):
        ''' docstring stub '''

    def middle_press(self):
        ''' docstring stub '''

    def middle_release(self):
        ''' docstring stub '''

    def all_release(self):
        ''' docstring stub '''

    # cato keyboard actions
    def press_enter(self):
        ''' docstring stub '''

    # ToDo, the rest of the keyboard buttons