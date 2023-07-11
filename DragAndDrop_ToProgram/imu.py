# SPDX-FileCopyrightText: Copyright (c) 2020 Bryan Siepert for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
This module provides the `adafruit_lsm6ds.ism330dhcx` subclass of LSM6DS sensors
==================================================================================
"""
from time import sleep

from adafruit_lsm6ds import LSM6DS, LSM6DS_DEFAULT_ADDRESS, RWBit, RWBits, const, ROUnaryStruct

import digitalio
import asyncio
import busio 
import countio

import time
import board
import gc
import supervisor as sp

from ulab import numpy as np

#from StrUUIDService import config
#from StrUUIDService import DebugStream

from math import pi, sin, cos, sqrt, asin

try:
    import typing  # pylint: disable=unused-import
    from busio import I2C
except ImportError:
    pass

# numpy for vector manipulation
from ulab import numpy as np

'''
    The Procedure I will use for rotation is as follows:

    1. Determine Which way is "Down" from Gravity
    2. Compare to 

    For rotation R about unit vector n through an angle of theta:
        The angle to be rotated through is theta: determined by the equation n1 x n2 = |n1| |n2| sin(theta)
        (n1 is the unit vector "down" for Cato, n2 is "down" as determined by gravity)
        arcsin(n1 x n2 / |n1||n2|) = theta

    Finally, the rotation is carried out about n = n1 x n2 / |n1 x n2|

    With R and Theta predefined, we need a rotation, which is given by the quaternion rotation equation:
        p'      = q p q^(-1); p' is rotated vector, q is quaternion as defined by, q^(-1) is it's conjugate
        q       = cos(theta/2) + n*sin(theta/2) OR q = [ q0, q1, q2, q3 ] = [cos(theta/2), ijk(sin(theta/2))]
        q^(-1)  = cos(theta/2) - n*sin(theta/2)

    Subsequently, the quaternion can be converted to a rotation matrix as
        [
            1 - 2q2^2 - 2q3^2   ;       2q1q2 - 2q0q3       ;   2q1q3 - 2q0q2
            2q1q2 + 2q0q3       ;       1 - 2q1^2 - 2q3^2   ;   2q2q3 - 2q0q1
            2q1q3 - 2q0q2       ;       2q2q3 + 2q0q1       ;   1 - 2q1^2 - 2q2^2
        ]
'''

# Generate Quaternion for rotation by Theta Through angle N. Rotated = q_t original q
q_gen = lambda n, theta: np.array([cos(theta/2.0), sin(theta/2.0) * n[0], sin(theta/2.0) * n[1], sin(theta/2.0) * n[2]])

# Quaternion rotation matrix, method two from https://danceswithcode.net/engineeringnotes/quaternions/quaternions.html (eqn 7b)
rot_mat = lambda q: np.array(
    [
        [ 1 - 2 * (q[2]**2 + q[3]**2),      2 * (q[1]*q[2] - q[0]*q[3]),        2 * (q[1]*q[3] + q[0]*q[2]) ],
        [ 2 * (q[1]*q[2] + q[0]*q[3]),      1 - 2 * (q[1]**2 + q[3]**2),        2 * (q[2]*q[3] - q[0]*q[1]) ],
        [ 2 * (q[1]*q[3] - q[0]*q[2]),      2 * (q[2]*q[3] + q[0]*q[1]),        1 - 2 * (q[1]**2 + q[2]**2) ]
    ]
)

_LSM6DS_INT1_CTRL   = const(0x0D)

_LSM6DS_CTRL1_XL    = const(0x10)
_LSM6DS_CTRL10_C    = const(0x19)
_LSM6DS_MASTER_CFG  = const(0x1A)

_LSM6DS_STATUS_REG  = const(0x1E) # This is a read only

_LSM6DS_TAP_CFG     = const(0x58)
_LSM6DS_TAP_THS_6D  = const(0x59)

_LSM6DS_INT_DUR2    = const(0x5A)
_LSM6DS_WAKE_UP_THS = const(0x5B)
_LSM6DS_WAKE_UP_DUR = const(0x5C)

_LSM6DS_MD1_CFG     = const(0x5E)

_LSM6DS_SM_THS      = const(0x13)

class LSM6DS3TRC(LSM6DS):   # pylint: disable=too-many-instance-attributes
    CHIP_ID = 0x6A # LSM address on nRF52840

    # config info at:
    # https://cdn.sparkfun.com/assets/learn_tutorials/4/1/6/AN4650_DM00157511.pdf
    _status_reg = ROUnaryStruct(    _LSM6DS_STATUS_REG,     "<b")

    _int1_ctrl      = RWBits(7,     _LSM6DS_INT1_CTRL,      0   ) # "The pad's output will supply the OR combination of all enabled signals"
    _ctrl1_xl       = RWBits(7,     _LSM6DS_CTRL1_XL,       0   )
    _ctrl10_c       = RWBits(7,     _LSM6DS_CTRL10_C,       0   )
    _master_cfg     = RWBits(7,     _LSM6DS_MASTER_CFG,     0   )
    
    _tap_cfg        = RWBits(7,     _LSM6DS_TAP_CFG,        0   )
    _tap_ths_6d     = RWBits(7,     _LSM6DS_TAP_THS_6D,     0   ) # [4D orientation (no z axis), sixd_ths(1:0), tap_ths(4:0)]
    _int_dur2       = RWBits(7,     _LSM6DS_INT_DUR2,       0   )
    _wake_up_ths    = RWBits(7,     _LSM6DS_WAKE_UP_THS,    0   )
    _wake_up_dur    = RWBits(7,     _LSM6DS_WAKE_UP_DUR,    0   )
    _sm_ths         = RWBits(7,     _LSM6DS_SM_THS,         0   ) # Significant Motn threshold [7:0] (Default 0x06)
    _md1_cfg        = RWBits(7,     _LSM6DS_MD1_CFG,        0   )

    def __init__(self, address: int = LSM6DS_DEFAULT_ADDRESS) -> None:
        
        # Enable Imu Power
        self._pwr = digitalio.DigitalInOut(board.IMU_PWR)
        self._pwr.direction = digitalio.Direction.OUTPUT
        self._pwr.value = True
        time.sleep(0.1) # mandatory imu bootup delay

        # Open i2c communication
        self.i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        super().__init__(self.i2c, address)

        # Establish flags
        self.imu_enable = asyncio.Event()   # enable:       Whether imu should allow reads
        self.imu_ready  = asyncio.Event()   # imu_rdy:      Set when imu has fresh data
        self.data_ready = asyncio.Event()   # data_rdt:     Set when imu data has been read and assigned to values
        self.tap_detect = asyncio.Event()   # tap_detect:   Set when imu interrupt 1 detects tap.

        # Build fields
        self.acc        = np.array([0.0, 0.0, 0.0]) # accelerometer fields
        self.gyro_vals  = np.array([0.0, 0.0, 0.0]) # gyro fields
        self.gyro_trim  = np.array([0.0, 0.0, 0.0]) # Gyroscope trim values set by calibrate

        # Rotational Adjustment Values (From Calibrate)
        # Default to Identity
        self.rot_mat = np.array([
            [1.0, 0.0, 0.0], 
            [0.0, 1.0, 0.0], 
            [0.0, 0.0, 1.0]
        ])

        # Configure IMU for accel and gyro stream
        self.data_ready_on_int1_setup()

        self.tasks = {
            "interrupt" : asyncio.create_task( self.interrupt() ),
            "read"      : asyncio.create_task( self.read() ),
            # "stream"    : asyncio.create_task( self.stream() )
        }

        # if(config["operation_mode"] == 12):
        #     self.tasks["imu_stream"] = asyncio.create_task( self.stream() )
    
    def data_ready_on_int1_setup(self):
        self.int1_ctrl = 0x02
 
    def sign_motn_ena(self):
        self._sm_ths        = 0x06 # significant motion threshold [7:0] (default 0x06)
        self.int1_ctrl      = 0x40 # step_detector, int1_Sign_motn, int1FullFlag, int1FIFO_OVR, int1_Fth, int1_Boot, int1DrdyG, int1DrdyXL
        self._ctrl10_c      = 0x05 # WristTiltEn, 0, TimerEn, PedoEn, TiltEn, FuncEn, PedoRST_Step, Sign_Motn_En

    def tap_ena(self):
        # Don't call this, instead, call single, double, or single-double
        self.int1_ctrl      = 0x00 # step_detector, int1_Sign_motn, int1FullFlag, int1FIFO_OVR, int1_Fth, int1_Boot, int1DrdyG, int1DrdyXL
        self._ctrl1_xl      = 0x60 # accelerometer ODR (output data rate) control
        self._tap_cfg       = 0x8E # int_ena, inact_ena1, inact ena0, slope_fds, tap_x, tap_y, tap_z, latched interrupt
        self._tap_ths_6d    = 0x8B # d4d (4d direction), 6d_ths[1:0], tap_ths[4:0]
        self._int_dur2      = 0x13 # Dur[3:0], Quiet[1:0], Shock[1:0]
        # self._wake_up_ths   = 0x80 # SingleDoubleTap, Inactivity, Wk_Ths[5:0]
        # self._ctrl10_c     = 0x05 # WristTiltEn, 0, TimerEn, PedoEn, TiltEn, FuncEn, PedoRST_Step, Sign_Motn_En
        # SELECT A TAP WITH SINGLE OR DOUBLE

    def tap_wake_cfg(self):
        self.tap_ena()
        self._md1_cfg     = 0x40 # Int1_Inact, SGL_Tap, Wakeup, Freefall, Doubletap, 6D, Tilt, Timer
        print("Single tap: Configured")

    def single_tap_cfg(self):
        self.tap_ena()
        self._md1_cfg   = 0x40
        

    def double_tap_cfg(self):
        self.tap_ena()
        self._md1_cfg     = 0x08 # Inactivity, SGL_Tap, Wakeup, Freefall, Doubletap, 6D, Tilt, Timer
    
    def sgl_dbl_tap_cfg(self):
        self.tap_ena()
        self._md1_cfg = 0x48

    @property
    def pwr(self):
        return self._pwr.value

    @pwr.setter
    def pwr(self, state : bool):
        self._pwr.value = state
        time.sleep(0.1) # time for imu to boot

    async def interrupt(self):
        """ interrupt signal from pin """
        print("interrupt task spawned")
        with countio.Counter(board.IMU_INT1, edge = countio.Edge.RISE) as interrupt:
            self.spark() # grab a few samples - guarantees a rising edge
            while True:
                await asyncio.sleep(0)      # release    
                if interrupt.count > 0:     # if rising edge seen
                    interrupt.count = 0     # reset
                    self.imu_ready.set()    # indicate detection

    async def read(self):
        ''' reads data off of the IMU into -> gx, gy, gz, ax, ay, az '''
        # print(self.gyro) # WHY IS THIS HERE?
        cycles = 0
        collect_spacer = 5 # collect garbage every n cycles
        rad_to_deg = 360.0 / (2*3.1416)
        
        from WakeDog import WakeDog # Can this be at top?
        
        while True:
            await self.imu_ready.wait()
            
            # Memory manager - collect garbage every collect_spacer samples
            cycles = (cycles + 1) % collect_spacer
            if cycles == 0:
                gc.collect()
            
            self.imu_ready.clear()

            # Read gyroscope
            self.gyro_vals = np.array(self.gyro)
            self.gyro_vals *= rad_to_deg
 
            # Read accelerometer
            self.acc = np.array(self.acceleration)

            acc_mag = np.linalg.norm(self.acc)
            acc_dir = self.acc / acc_mag # unit vector

            # trim measurements based on calibration
            self.gyro_vals -= self.gyro_trim
            gyro_mag = np.linalg.norm(self.gyro_vals)
            
            # Apply pre-rotation with generated rotation matrix
            self.gyro_vals  = np.dot(self.rot_mat, self.gyro_vals)
            self.acc        = np.dot(self.rot_mat, self.acc)

            # Check sleep conditions
            thresh = 40 # TODO PULL THIS FROM CONFIG!!!
            if gyro_mag > thresh:
                WakeDog.feed()

            self.data_ready.set()

    async def wait(self):
        ''' await this function to sync wth next data-ready signal ''' 
        await self.data_ready.wait()
        self.data_ready.clear()

    async def calibrate(self, num_calib_cycles):
        from WakeDog import WakeDog
        print("Calibrating HOLD STILL")
        
        gyro_avg = np.array([0.0, 0.0, 0.0])

        for i in range(num_calib_cycles):
            await self.wait()
            gyro_avg    += self.gyro_vals
            WakeDog.feed()

        self.gyro_trim += gyro_avg / num_calib_cycles
        print("Done Calibrating")
    
    async def full_calibrate(self, num_calib_cycles):
        from WakeDog import WakeDog
        print("Calibrating HOLD STILL")
        
        gyro_avg = np.array([0.0, 0.0, 0.0])

        accel_avg = np.array([0.0, 0.0, 0.0])

        for i in range(num_calib_cycles):
            await self.wait()
            gyro_avg    += self.gyro_vals
            accel_avg   += self.acc
            
            WakeDog.feed()

        self.gyro_trim += gyro_avg / num_calib_cycles

        # Find Average Direction of Gravity Over Calibration 
        accel_avg /= num_calib_cycles
        grav_dir = accel_avg / np.linalg.norm(accel_avg)

        # describe desired endpoint of rotation
        down = np.array([0.0, -1.0, 0.0])

        # Rotation axis is in line with Crossproduct
        n = np.cross(grav_dir, down)
        mag_n = np.linalg.norm(n)
        
        n = n / mag_n # Normalize to Unit Vector

        # Angle is related by a cross b = |a||b|sin(angle)
        # We extract angle as angle = arcsin(a cross b)
        th = asin(mag_n)

        self.rot_mat = rot_mat( q_gen(n, th) )
        print("Done Calibrating")

    async def stream(self):
        #print("+ stream")
        while True:
            #print(": stream -> awaiting self.wait")
            await self.wait()
            print(f"Gyro: {self.gx :.2f}, {self.gy :.2f}, {self.gz :.2f} \tAccel: {self.ax :.2f}, {self.ay :.2f}, {self.az :.2f}")

    def spark(self):
        '''
            helper method for starting countio effect on interrupt
            data ready signal only appears after data is read 
                -- countio counts edges, if data constantly ready, countio always high, interrupt never triggers
        '''
        for i in range(3):
            temp_g, temp_a = self.gyro, self.acceleration

    @property
    def status(self) -> int:
        """get status"""
        return self._status_reg

    @property
    def gyro_ready(self) -> bool:
        return (self._status_reg & 2 > 0)

    @property
    def accel_ready(self) -> bool:
        return (self._status_reg & 1 > 0)

    @property
    def int1_ctrl(self) -> int:
        return (self._int1_ctrl)

    @int1_ctrl.setter
    def int1_ctrl(self, value: int) -> None:
        self._int1_ctrl = value
    
    @property
    def master_cfg(self) -> int:
        return (self._master_cfg)
    
    @master_cfg.setter
    def master_cfg(self, value: int) -> None:
        self._master_cfg = value

    @property
    def gx(self):
        return self.gyro_vals[0]
    
    @property
    def gy(self):
        return self.gyro_vals[1]
                              
    @property
    def gz(self):
        return self.gyro_vals[2]
    
    @property
    def ax(self):
        return self.acc[0]
    
    @property
    def ay(self):
        return self.acc[1]
                              
    @property
    def az(self):
        return self.acc[2]
    