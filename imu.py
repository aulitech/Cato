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

_LSM6DS_INT1_CTRL  = const(0x0D)
_LSM6DS_CTRL10_C = const(0x19)
_LSM6DS_STATUS_REG = const(0x1E)
_LSM6DS_MASTER_CFG = const(0x1A)

class LSM6DS3TRC(LSM6DS):   # pylint: disable=too-many-instance-attributes

    """Driver for the LSM6DS3TRC 6-axis accelerometer and gyroscope.

    :param ~busio.I2C i2c_bus: The I2C bus the device is connected to.
    :param int address: The I2C device address. Defaults to :const:`0x6A`


    **Quickstart: Importing and using the device**

        Here is an example of using the :class:`ISM330DHCX` class.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            from adafruit_lsm6ds.ism330dhcx import ISM330DHCX

        Once this is done you can define your `board.I2C` object and define your sensor object

        .. code-block:: python

            i2c = board.I2C()  # uses board.SCL and board.SDA
            sensor = ISM330DHCX(i2c)

        Now you have access to the :attr:`acceleration` and :attr:`gyro`: attributes

        .. code-block:: python

            acc_x, acc_y, acc_z = sensor.acceleration
            gyro_x, gyro_z, gyro_z = sensor.gyro


    """

    CHIP_ID = 0x6A
    # This version of the IMU has a different register for enabling the pedometer
    # https://www.st.com/resource/en/datasheet/lsm6ds3tr-c.pdf
    _ped_enable = RWBit(_LSM6DS_CTRL10_C, 4)
    _status_reg = ROUnaryStruct(_LSM6DS_STATUS_REG, "<b")
    _int1_ctrl = RWBits(7, _LSM6DS_INT1_CTRL, 0)
    _master_cfg = RWBits(7, _LSM6DS_MASTER_CFG, 0)
    

    #_gyro_range_4000dps = RWBit(_LSM6DS_CTRL2_G, 0)

    def __init__(self, address: int = LSM6DS_DEFAULT_ADDRESS) -> None:
        # print("imu init -- start")
        # enable imu
        self._pwr = digitalio.DigitalInOut(board.IMU_PWR)
        self._pwr.direction = digitalio.Direction.OUTPUT
        self._pwr.value = True
        time.sleep(0.1) # mandatory imu bootup delay

        self.i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)

        super().__init__(self.i2c, address)

        self.imu_enable = asyncio.Event()   # enable:   Whether imu should allow reads
        self.imu_ready  = asyncio.Event()   # imu_rdy:  Set when imu has fresh data
        self.data_ready = asyncio.Event()   # data_rdt: Set when imu data has been read and assigned to values

        self.ax, self.ay, self.az = 0, 0, 0 # accelerometer fields
        self.gx, self.gy, self.gz = 0, 0, 0 # gyro fields

        # Gyroscope trim values set by calibrate
        self.x_trim = 0
        self.y_trim = 0
        self.z_trim = 0
        
        # config info at:
        # https://cdn.sparkfun.com/assets/learn_tutorials/4/1/6/AN4650_DM00157511.pdf
        # here, we set the GDA bit of the INT1_CTRL register to True, 
        # to push Data Ready (gyro) signal to INT1 pin for interrupt
        self.int1_ctrl = 0x02

        self.tasks = {
            "interrupt" : self.interrupt(),
            "read"      : self.read(),
            #"stream"    : self.stream()
        }

        # self.ena.set()
        # print("imu init -- finish")

    @property
    def pwr(self):
        return self._pwr.value
    
    @pwr.setter
    def pwr(self, state : bool):
        self._pwr.value = state
        time.sleep(0.1) # time for imu to boot

    async def interrupt(self):
        """ interrupt on imu for gyro data ready """
        # print("interrupt -- await imu enable")
        await self.imu_enable.wait()
        with countio.Counter(   
            board.IMU_INT1, 
            edge = countio.Edge.RISE, 
            pull = digitalio.Pull.DOWN 
        ) as interrupt:
            self.spark()
            while True:
                await asyncio.sleep(0)
                # print("IMU Start: ", gc.mem_free())
                if interrupt.count > 0:
                    interrupt.count = 0
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
            # hold until data ready
            # print("read -- awaiting imu_ready")
            
            # print("A: ", gc.mem_free())
            await self.imu_ready.wait()
            cycles = (cycles + 1) % collect_spacer
            if cycles == 0:
                gc.collect()
            # print("B: ", gc.mem_free())
            
            self.imu_ready.clear()
            # read from IMU
            self.gx, self.gy, self.gz = self.gyro
            # print("C: ", gc.mem_free())

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