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
import board
import busio 
import asyncio
import time
import countio
from math import pi
import gc
# import supervisor as sp
try:
    import typing  # pylint: disable=unused-import
    from busio import I2C
except ImportError:
    pass

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

class LSM6DS3TRC(LSM6DS):   # pylint: disable=too-many-instance-attributes
    CHIP_ID = 0x6A
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
    
    _md1_cfg        = RWBits(7,     _LSM6DS_MD1_CFG,        0   )

    def __init__(self, address: int = LSM6DS_DEFAULT_ADDRESS) -> None:
        # print("imu init -- start")
        # enable imu
        self._pwr = digitalio.DigitalInOut(board.IMU_PWR)
        self._pwr.direction = digitalio.Direction.OUTPUT
        self._pwr.value = True
        time.sleep(0.1) # mandatory imu bootup delay

        self.i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)

        super().__init__(self.i2c, address)

        self.imu_enable = asyncio.Event()   # enable:       Whether imu should allow reads
        self.imu_ready  = asyncio.Event()   # imu_rdy:      Set when imu has fresh data
        self.data_ready = asyncio.Event()   # data_rdt:     Set when imu data has been read and assigned to values
        self.tap_detect = asyncio.Event()   # tap_detect:   Set when imu interrupt 1 detects tap.
        self.ax, self.ay, self.az = 0, 0, 0 # accelerometer fields
        self.gx, self.gy, self.gz = 0, 0, 0 # gyro fields

        # Gyroscope trim values set by calibrate
        self.x_trim = 0
        self.y_trim = 0
        self.z_trim = 0
        
        self.data_ready_on_int1_setup()

        self.tasks = {
            "interrupt" : self.interrupt(),
            "read"      : self.read(),
            #"stream"    : self.stream()
        }
    
    def data_ready_on_int1_setup(self):
        self.int1_ctrl = 0x02
    
    def mode_setup(self):
        pass
        # self._ctrl1_xl      = 0x60 # accelerometer ODR control
        # self._tap_cfg       = 0x0D # timer, pedo, tilt, slope_fds, tap_x, tap_y, tap_z, latched interrupt
        # self._tap_ths_6d    = 0x81 # d4d (4d direction), 6d_ths[1:0], tap_ths[4:0]
        # self._int_dur2      = 0x7F # Dur[3:0], Quiet[1:0], Shock[1:0]
        # self._wake_up_ths   = 0x02 # SingleDoubleTap, Inactivity, Wk_Ths[5:0]
        # self._wake_up_dur   = 0x00 # FF_Dur5, Wake_Dur1, Wake_Dur0, TimerHR, Sleep_Dur[3:0]
        # self._md1_cfg       = 0x24 # Inactivity, SGL_Tap, Wakeup, Freefall, Doubletap, 6D, Tilt, Timer
        # _master_cfg         = 0x00 # DRDY_ON_INT1, DATA_VALID_SEL_FIFO, 0, START_CONFIG, PULL_UP_EN, PASS_THROUGH_MODE, IRON_EN, MASTER_ON

    def single_tap_cfg(self):
        self._ctrl1_xl    = 0x60 # accelerometer ODR (output data rate) control
        self._tap_cfg     = 0x8E # timer, pedo, tilt, slope_fds, tap_x, tap_y, tap_z, latched interrupt
        self._tap_ths_6d  = 0x8C # d4d (4d direction), 6d_ths[1:0], tap_ths[4:0]
        self._int_dur2    = 0x7F # Dur[3:0], Quiet[1:0], Shock[1:0]
        self._wake_up_ths = 0x80 # SingleDoubleTap, Inactivity, Wk_Ths[5:0]
        self._md1_cfg     = 0x40 # Inactivity, SGL_Tap, Wakeup, Freefall, Doubletap, 6D, Tilt, Timer

    def double_tap_cfg(self):
        self._ctrl1_xl    = 0x60 # accelerometer ODR control
        self._tap_cfg     = 0x8E # timer, pedo, tilt, slope_fds, tap_x, tap_y, tap_z, latched interrupt
        self._tap_ths_6d  = 0x8C # d4d (4d direction), 6d_ths[1:0], tap_ths[4:0]
        self._int_dur2    = 0x7F # Dur[3:0], Quiet[1:0], Shock[1:0]
        self._wake_up_ths = 0x80 # SingleDoubleTap, Inactivity, Wk_Ths[5:0]

        #for double tap, md1_cfg = 0x08
        self._md1_cfg     = 0x08 # Inactivity, SGL_Tap, Wakeup, Freefall, Doubletap, 6D, Tilt, Timer
        
    @property
    def pwr(self):
        return self._pwr.value

    @pwr.setter
    def pwr(self, state : bool):
        self._pwr.value = state
        time.sleep(0.1) # time for imu to boot

    async def interrupt(self):
        """ interrupt on imu for gyro data ready """
        print("Interrupt task is live")
        with countio.Counter(   
            board.IMU_INT1, 
            edge = countio.Edge.RISE
        ) as interrupt:
            self.spark()
            while True:
                await asyncio.sleep(0)
                # print("IMU Start: ", gc.mem_free())
                if interrupt.count > 0:
                    interrupt.count = 0
                    # print("Interrupt")
                    self.imu_ready.set()
                # print("IMU End: ", gc.mem_free())

    async def read(self):
        ''' reads data off of the IMU into -> gx, gy, gz, ax, ay, az '''
        # print("Quick read of gyro -- once at top of imu.read")
        # print(self.gyro)
        cycles = 0
        collect_spacer = 10 # collect garbage every n cycles
        rad_to_deg = 360.0 / (2*3.1416)
        while True:
            await self.imu_ready.wait()
            cycles = (cycles + 1) % collect_spacer
            if cycles == 0:
                gc.collect()
            
            self.imu_ready.clear()
            self.gx, self.gy, self.gz = self.gyro

            self.gx *= rad_to_deg
            self.gy *= rad_to_deg
            self.gz *= rad_to_deg
            self.ax, self.ay, self.az = self.acceleration

            # trim measurements based on calibration
            self.gx -= self.x_trim
            self.gy -= self.y_trim
            self.gz -= self.z_trim
            
            # print("D: ", gc.mem_free())
            self.data_ready.set()
            # print("" )
            # print("- end of read_imu -")

    async def wait(self):
        ''' await this function to sync wth next data-ready signal '''
        # print("wait -- awaiting data-ready")
        
        await self.data_ready.wait()
        self.data_ready.clear()

    async def calibrate(self, num_calib_cycles):
        print("Calibrating HOLD STILL")
        x = 0.0
        y = 0.0
        z = 0.0
        for i in range(num_calib_cycles):
            # print(f"num: {i}")
            await self.wait()
            x += self.gx
            y += self.gy
            z += self.gz
        self.x_trim = x / num_calib_cycles
        self.y_trim = y / num_calib_cycles
        self.z_trim = z / num_calib_cycles
        print("Done Calibrating")

    async def stream(self):
        while True:
            # print("stream -- awaiting self.wait")
            await self.wait()
            print(f"{self.gx}, {self.gy}, {self.gz}")

    def spark(self):
        '''
            helper method for starting countio effect on interrupt
            data ready signal only appears after data is read 
                -- countio counts edges, if data constantly ready, countio always high, interrupt never triggers
        '''
        # print("SPARK!")
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