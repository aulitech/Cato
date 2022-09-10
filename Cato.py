from math import sqrt
import board
import busio
import time
import digitalio

from adafruit_lsm6ds.lsm6ds3trc import LSM6DS3TRC

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse


import adafruit_ble
from adafruit_ble.advertising import Advertisement
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService

from adafruit_lsm6ds.lsm6ds3trc import LSM6DS3TRC

import BluetoothControl

import math

class Cato:
    def __init__(self):
        self.sensor = "IMU not setup"
        self._setup_IMU()
        self.Blue = BluetoothControl.BluetoothControl()
        # On the Seeed XIAO Sense the LSM6DS3TR-C IMU is connected on a separate
        # I2C bus and it has its own power pin that we need to enable.
        self.Blue.connectBluetooth()

    def _setup_IMU(self):
        imupwr = digitalio.DigitalInOut(board.IMU_PWR)
        imupwr.direction = digitalio.Direction.OUTPUT
        imupwr.value = True
        time.sleep(0.1)
        imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        self.sensor = LSM6DS3TRC(imu_i2c)

        self.gx, self.gy, self.gz = self.sensor.gyro
        self.ax, self.ay, self.az = self.sensor.acceleration
        self.acc = [self.ax, self.ay, self.az]
        self.gyr = [self.ax, self.gx, self.gz]
    
    def read_IMU(self):
        self.gx, self.gy, self.gz = self.sensor.gyro
        self.ax, self.ay, self.az = self.sensor.acceleration
        self.gyr = [self.ax, self.gx, self.gz]
        self.acc = [self.ax, self.ay, self.az]

    def move_Mouse(self):
        idle = False
        idle_count = 0
        max_idle_cycles = 100
        idle_thresh = 1.0
        #MOUSE_TYPE = "LINEAR"
        MOUSE_TYPE = "ACCEL"
        slow_thresh = 1.8
        fast_thresh = 5.0
        scale = 1.0
        sleep_time = 0.015 #per cycle seconds to delay
        idle_time = 0.5 #seconds to idle before exiting
        max_idle_cycles = int(idle_time / sleep_time)
        while(idle_count < max_idle_cycles):
            time.sleep(sleep_time)
            self.read_IMU()
            x_mvmt = 10 * self.gy
            y_mvmt = 10 * self.gz
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = math.atan2(y_mvmt, x_mvmt)
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
                #print("idle detected (%d)" % idle_count)
                idle_count += 1
            else:
                #print("RESET BY MOTION")
                idle_count = 0
            x_amt = scale * math.cos(ang)
            y_amt = scale * math.sin(ang)
            #print("rate: %s, x: %f, y: %f" % (scale_str, x_amt, y_amt))
            self.Blue.mouse.move(int(x_amt), int(y_amt), 0)
