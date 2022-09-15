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

""" #helpers and enums """
#enum states
class ST():
    IDLE = 0
    MOUSE_BUTTONS = 1
    KEYBOARD = 2

#enum events
class EV():
    NONE = 0
    UP = 1
    DOWN = 2
    RIGHT = 3
    LEFT = 4
    ROLL_R = 5
    ROLL_L = 6
    SHAKE_YES = 7
    SHAKE_NO = 8

""" main class """
class Cato:
    """ setup methods """
    def __init__(self):
        self._setup_IMU()
        self.Blue = BluetoothControl()
        self.Blue.connectBluetooth()
        self.stMatrix = [
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
        
    def _setup_IMU(self):
        imupwr = digitalio.DigitalInOut(board.IMU_PWR)
        imupwr.direction = digitalio.Direction.OUTPUT
        imupwr.value = True
        time.sleep(0.1)
        imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        self.sensor = LSM6DS3TRC(imu_i2c)

        self.gx, self.gy, self.gz = self.sensor.gyro
        self.ax, self.ay, self.az = self.sensor.acceleration        
    
    """ State Control / Execution Utils """
    def detectEvent(self):
        return EV.NONE
    def dispatchEvent(self, event):
        self.stMatrix[event][self.state]()
    
    """ Sensor utils read_IMU, calibrate"""
    def read_IMU(self):
        self.gx, self.gy, self.gz = self.sensor.gyro
        self.ax, self.ay, self.az = self.sensor.acceleration

    """ Cato Actions """
    """ CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse """
    def noop(self):
        print("nooping")
        pass
    
    """ Cato Mouse Actions """
    def moveMouse(self):
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
            self.read_IMU()
            x_mvmt = 10 * self.gy
            y_mvmt = 10 * self.gz
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = atan2(y_mvmt, x_mvmt)
            scale_str = "linear"
            #control mouse scale / type
            if(MOUSE_TYPE == "LINEAR"):    
                pass
            if(MOUSE_TYPE == "ACCEL"):
                if(mag <= slow_thresh):
                    scale_str = "slow"
                    scale = mag*1.0
                elif(mag > slow_thresh and mag <= fast_thresh):
                    scale_str = "mid"
                    scale = mag*2.5
                else:
                    scale_str = "fast"
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
            self.Blue.mouse.move(int(x_amt), int(y_amt), 0)
    
    def scroll(self):
        while (not True):
            scroll_amt = 0
            self.Blue.mouse.move(0, 0, scroll_amt)
        pass
    
    #shift + scroll = lateral scroll on MOST applications
    def scroll_LR(self):
        #press shift
        while(not True):
            self.Blue.mouse.move(0, 0, scroll_amt)
        #release shift
        pass

    def leftClick(self):
        pass
    
    def rightClick(self):
        pass
    
    def middleClick(self):
        pass

    def leftClickDrag(self):
        pass

    def rightClickDrag(self):
        #possible utility on omnidirectional scroll
        pass

    def leftPress(self):
        pass

    def leftRelease(self):
        pass

    def rightPress(self):
        pass

    def rightRelease(self):
        pass

    def middlePress(self):
        pass

    def middleRelease(self):
        pass

    def allRelease(self):
        pass
    
    """ Cato Keyboard Actions """
    def pressEnter(self):
        pass

    # To Do, soon
