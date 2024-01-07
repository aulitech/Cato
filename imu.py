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
from utils import stopwatch
from ulab import numpy as np

from utils import config

from math import pi, sin, cos, sqrt, asin

try:
    import typing  # pylint: disable=unused-import
    from busio import I2C
except ImportError:
    pass

# numpy for vector manipulation
from ulab import numpy as np

import re

_LSM6DS_INT1_CTRL   = const(0x0D)

_LSM6DS_CTRL1_XL    = const(0x10)
_LSM6DS_CTRL4_C     = const(0x13)
_LSM6DS_CTRL6_C     = const(0x15)
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
    # https://www.st.com/resource/en/datasheet/lsm6ds3tr-c.pdf
    _status_reg = ROUnaryStruct(    _LSM6DS_STATUS_REG,     "<b") # [0, 0, 0, 0, 0, TempDA, GyrDA, XLDA]

    _int1_ctrl      = RWBits(7,     _LSM6DS_INT1_CTRL,      0   ) # [step, sig_mot, fifo_full, fifo_ovr, fifo_ths, boot, drdy_g, drdy_xl]
    _ctrl1_xl       = RWBits(7,     _LSM6DS_CTRL1_XL,       0   ) # [odr_xl(3:0), fs_xl(1:0), lpf_bw_sel, bw0_xl]
    _ctrl4_c        = RWBits(7,     _LSM6DS_CTRL4_C,        0   ) # [den_xl_en, sleep, den_drdy_int1, int2_on_int1, drdy_mask, i2c_disable, lpf1_sel_g]
    _ctrl6_c        = RWBits(7,     _LSM6DS_CTRL6_C,        0   ) # [Trig_en, lvl_en, lvl2_en, xl_hm_mode, usr_off_w, 0, ftype[1:0]]
    _ctrl10_c       = RWBits(7,     _LSM6DS_CTRL10_C,       0   ) # [wrist_tilt_en, timer_en, pedo_en, tilt_en, func_en, pedo_rst_step, sign_motion_en]
    _master_cfg     = RWBits(7,     _LSM6DS_MASTER_CFG,     0   ) # [drdy_on_int1, data_valid_sel_fifo, 0, start_config, pull_up_en, pass_through_mode, iron_en, master_on]
    _tap_cfg        = RWBits(7,     _LSM6DS_TAP_CFG,        0   ) # [int_ena, inact_en1, inact_en(1:0), slope_fds, tapx, tapy, tapz, lir]
    _tap_ths_6d     = RWBits(7,     _LSM6DS_TAP_THS_6D,     0   ) # [4D orientation (no z axis), sixd_ths(1:0), tap_ths(4:0)]
    _int_dur2       = RWBits(7,     _LSM6DS_INT_DUR2,       0   ) # [dur(3:0), quiet(1:0), shock(1:0)]
    _wake_up_ths    = RWBits(7,     _LSM6DS_WAKE_UP_THS,    0   ) # [single_double_tap, 0, wake_ths(5:0)]
    _wake_up_dur    = RWBits(7,     _LSM6DS_WAKE_UP_DUR,    0   ) # [ff_dur5, wake_dur[1:0], timer_hr, sleep_dur[3:0]]
    _md1_cfg        = RWBits(7,     _LSM6DS_MD1_CFG,        0   ) # [int1_inact_state, int1_single_tap, int1_wu, int1_ff, int1_double_tap, int1_6d, int1_tilt, int1_timer]
    _sm_ths         = RWBits(7,     _LSM6DS_SM_THS,         0   ) # Significant Motn threshold [7:0] (Default 0x06)

    def __init__(self, address: int = LSM6DS_DEFAULT_ADDRESS) -> None:
        
        # Enable Imu Power
        self._pwr = digitalio.DigitalInOut(board.IMU_PWR)
        self._pwr.direction = digitalio.Direction.OUTPUT
        self._pwr.value = True
        time.sleep(0.1) # mandatory imu bootup delay

        # Open i2c communication
        self.i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
        super().__init__(self.i2c, address)
        # self.ctrl4_c = 0x02
        # self.ctrl6_c = 0x03

        # Establish flags
        self.imu_enable = asyncio.Event()   # enable:       Whether imu should allow reads
        self.imu_ready  = asyncio.Event()   # imu_rdy:      Set when imu has fresh data
        self.data_ready = asyncio.Event()   # data_rdy:     Set when imu data has been read and assigned to values
        self.tap_type = None # 1 for single, 2 for double

        # Build fields
        self.acc        = np.array([0.0, 0.0, 0.0]) # accelerometer fields
        self.gyro_vals  = np.array([0.0, 0.0, 0.0]) # gyro fields

        # Calibration params
        self.gyro_trim  = config["calibration"]["drift"] # Gyroscope trim values set by calibrate
        self.not_calibrated = True
        self.autoCalibLen = config["calibration"]["auto_samples"]
        self.autoCalibThresh = config["calibration"]["auto_threshold"]
        self.sleep_thresh = config["sleep"]["threshold"]

        # Rotational Adjustment Values (From Calibrate)
        # Default to Identity
        self.rot_mat = np.array([
            [1.0, 0.0, 0.0], 
            [0.0, 1.0, 0.0], 
            [0.0, 0.0, 1.0]
        ])

        # load tap config settings
        self.tap_ths_6d =  0x1F & 11
        self.int_dur2 = ( (0x1F) & (2 << 2) ) | 2
        if(config['operation_mode'] == 'clicker'):
            self.tap_ths_6d = 0x1F & config['clicker']['tap_ths']
            self.int_dur2   = ( (0x1F) & (config['clicker']['quiet'] << 2) ) | config['clicker']['shock']

        # Configure IMU for accel and gyro stream
        self.data_ready_on_int1_setup()
        
        self.tasks = {}

        if config["operation_mode"] == "clicker": # TODO: if clicker in op_mode
            self.tasks.update({"read_click" : asyncio.create_task(self.read_clicks())})
        else:
            self.tasks.update({"read"      : asyncio.create_task( self.read() )})
        if config['operation_mode'] == "stream_imu":
            self.tasks.update({'stream' : asyncio.create_task( self.stream() )})
        self.tasks.update({"interrupt" : asyncio.create_task( self.interrupt() ) })

    
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
    def setup_type(self):
        if(self.int1_ctrl == 0x00):
            return "tap"
        elif(self.int1_ctrl == 0x02):
            return "gyro"
 
    def sig_mot_ena(self):
        # self._sm_ths        = 0x06 # significant motion threshold [7:0] (default 0x06)
        # print(self._sm_ths)
        self.int1_ctrl      = 0x40 # step_detector, int1_Sign_motn, int1FullFlag, int1FIFO_OVR, int1_Fth, int1_Boot, int1DrdyG, int1DrdyXL
        self._ctrl10_c      = 0x05 # WristTiltEn, 0, TimerEn, PedoEn, TiltEn, FuncEn, PedoRST_Step, Sign_Motn_En

    def data_ready_on_int1_setup(self):
        self.int1_ctrl = 0x02
    
    def tap_ena(self):
        self.int1_ctrl      = 0x00 # step_detector, int1_Sign_motn, int1FullFlag, int1FIFO_OVR, int1_Fth, int1_Boot, int1DrdyG, int1DrdyXL
        self._ctrl1_xl      = 0x60 # accelerometer ODR (output data rate) control
        self._tap_cfg       = 0x8E # int_ena, inact_ena1, inact ena0, slope_fds, tap_x, tap_y, tap_z, latched interrupt
        if config['operation_mode'] == 'clicker':
            self._tap_ths_6d    = 0x1F & config['clicker']['tap_ths'] # d4d (4d direction), 6d_ths[1:0], tap_ths[4:0]
            self._int_dur2      = ( (0x1F) & (config['clicker']['quiet'] << 2) ) | config['clicker']['shock'] # Dur[3:0], Quiet[1:0], Shock[1:0]
        else: # Default Value
            self._tap_ths_6d    = 0x1F & 11 
            self._int_dur2      = ( (0x1F) & 2 << 2) | 2 # Dur[3:0], Quiet[1:0], Shock[1:0]

    def single_tap_cfg(self):
        print("Single Tap Config")
        self.tap_ena()
        self._md1_cfg   = 0x40

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

        calibCycles = 0
        trimAdjust = np.array((0,0,0))
        gyro_prev = np.array((0,0,0))
        
        while True:
            await self.imu_ready.wait()
            
            # Memory manager - collect garbage every collect_spacer samples
            cycles = (cycles + 1) % collect_spacer
            if cycles == 0:
                gc.collect()
            
            self.imu_ready.clear()

            # Save previous gyro for trim adjustment
            #gyro_prev = self.gyro_vals

            # Read gyroscope
            self.gyro_vals = np.array(self.gyro)
            self.gyro_vals *= rad_to_deg
 
            # Read accelerometer
            self.acc = np.array(self.acceleration)

            acc_mag = np.linalg.norm(self.acc)
            acc_dir = self.acc / acc_mag # unit vector

            # Apply pre-rotation with generated rotation matrix
            self.gyro_vals  = np.dot(self.rot_mat, self.gyro_vals)
            self.acc        = np.dot(self.rot_mat, self.acc)

            # trim measurements based on calibration
            self.gyro_vals -= self.gyro_trim
            gyro_mag = np.linalg.norm(self.gyro_vals)

            if(self.not_calibrated):
                gyro_delta_mag = np.linalg.norm(self.gyro_vals - gyro_prev)

                if(calibCycles == self.autoCalibLen):
                    print("...calibrated...")
                    for i in range(len(self.gyro_trim)):
                        self.gyro_trim[i] += trimAdjust[i]
                    self.gyro_vals -= trimAdjust
                    gyro_prev = self.gyro_vals
                    calibCycles = 0
                    trimAdjust = np.array((0,0,0))

                if(gyro_delta_mag < self.autoCalibThresh):
                    calibCycles += 1
                    trimAdjust += self.gyro_vals / self.autoCalibLen
                else:
                    gyro_prev = self.gyro_vals
                    calibCycles = 0
                    trimAdjust = np.array((0,0,0))
            
            # Check sleep conditions
            thresh = self.sleep_thresh
            if gyro_mag > thresh:
                WakeDog.feed()

            self.data_ready.set()

    async def read_clicks(self):
        click_spacing = config["clicker"]["max_click_spacing"]
        timeout_ev = asyncio.Event()
        timeout_ev.clear()
        max_clicks = len(config["bindings"])-1
        print("Max Clicks: ", max_clicks)
        while True:
            # print("Read Click Awaiting")
            await self.imu_ready.wait()
            # print("Read Click Get ")
            #Reset tap_type and timer
            self.tap_type = 0 # passed first imu_ready - already have one tap
            timeout_ev.clear()

            # create timer and restart it each time a tap occurs
            sw = None

            while (not timeout_ev.is_set()) and (self.tap_type < max_clicks):
                if self.imu_ready.is_set():
                    # print("imu awaiting inside")
                    self.tap_type += 1
                    if sw is not None:
                        sw.cancel()
                    sw = asyncio.create_task( stopwatch(click_spacing, timeout_ev) )
                    self.imu_ready.clear()
                await asyncio.sleep(0)
            print("TAP TYPE: ", self.tap_type)
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

        for i in range(len(self.gyro_trim)):
            self.gyro_trim[i] += gyro_avg[i] / num_calib_cycles
        
        # self.not_calibrated = False
        print("Done Calibrating")
    
    # async def full_calibrate(self, num_calib_cycles):
    #     from WakeDog import WakeDog
    #     print("Calibrating HOLD STILL")
        
    #     gyro_avg = np.array([0.0, 0.0, 0.0])
    #     accel_avg = np.array([0.0, 0.0, 0.0])

    #     for i in range(num_calib_cycles):
    #         await self.wait()
    #         gyro_avg    += self.gyro_vals
    #         accel_avg   += self.acc
            
    #         WakeDog.feed()

    #     for i in range(len(self.gyro_trim)):
    #         self.gyro_trim[i] += gyro_avg[i] / num_calib_cycles

    #     # Find Average Direction of Gravity Over Calibration 
    #     accel_avg /= num_calib_cycles
    #     grav_dir = accel_avg / np.linalg.norm(accel_avg)
    #     print(grav_dir)

    #     # describe the most aligned "down" direction
    #     grav = np.array([0.0, 0.0, 0.0])
    #     grav_axis = np.argmax( abs(grav_dir) )
    #     grav[ grav_axis ] = 1 if (grav_dir[grav_axis] > 0) else -1


    def reorient(self):
        #validate orientation strings
        ori_regex = re.compile('[+-][xyzXYZ]')
        
        x_screen_str = config['orientation']['bottom']
        y_screen_str = config['orientation']['left']
        roll_str = config['orientation']['front']

        for ax in [x_screen_str, y_screen_str, roll_str]:
            if ori_regex.match(ax) is None:
                raise ValueError("Invalid Orientation String")
        
        re.sub('[xX]', 'x', x_screen_str)
        re.sub('[yY]', 'y', y_screen_str)
        re.sub('[zZ]', 'z', roll_str)
        
        print(  "Top: " + x_screen_str + "\n" +
                "Left: " + y_screen_str + '\n' + 
                "Back:     " + roll_str 
        )

        top = np.array([
            1.0 if 'x' in x_screen_str else 0.0,
            1.0 if 'y' in x_screen_str else 0.0,
            1.0 if 'z' in x_screen_str else 0.0
        ])

        left = np.array([
            1.0 if 'x' in y_screen_str else 0.0,
            1.0 if 'y' in y_screen_str else 0.0,
            1.0 if 'z' in y_screen_str else 0.0
        ])

        front = np.array([
            1.0 if 'x' in roll_str else 0.0,
            1.0 if 'y' in roll_str else 0.0,
            1.0 if 'z' in roll_str else 0.0
        ])

        if '-' in roll_str:
            front *= -1

        if '-' in x_screen_str:
            top *= -1

        if '-' in y_screen_str:
            left *= -1

        if np.dot(top, left)   != 0.0:
            raise ValueError("Orientation of 'x' and 'y' are not perpendicular")
        if np.dot(left, front)       != 0.0:
            raise ValueError("Orientation of Roll and Y are not perpendicular")
        if np.dot(top, front)       != 0.0:
            raise ValueError("X and Roll not Perpendicular")

        # ORIGINAL ORIENTATION:
        # SCREEN_X  : +Y
        # SCREEN_Y  : +Z
        # ROLL      : +X

        # BOARD FRAME:
        # "Into USB-C" = "+X"
        # "Up out of top" = "+Z"

        x_col = front
        y_col = top
        z_col = left

        full_calib_msg = f"Reorient Result:\n"

        transform = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0]
        ])

        for row in range(3):
            transform[row][0] = x_col[row]
            transform[row][1] = y_col[row]
            transform[row][2] = z_col[row]

        transform = np.linalg.inv(transform)
        self.rot_mat = transform
        
        full_calib_msg += "\tMatrix:     \n"
        for row in self.rot_mat.tolist():
            full_calib_msg += '\t\t'
            for idx, entry in enumerate(row):
                full_calib_msg += f"{entry:<+6.1f}" + ( '\n' if (idx==2) else '' )
        full_calib_msg += f"\t Det: {np.linalg.det(transform)}"
        print(full_calib_msg)
        
    async def stream(self):
        #print("+ stream")
        while True:
            #print(": stream -> awaiting self.wait")
            await self.wait()
            print(f"Gyro: {self.gx :10.2f}, {self.gy :10.2f}, {self.gz :10.2f}" + 
                  f"\tAccel: {self.ax :10.2f}, {self.ay :10.2f}, {self.az :10.2f}")

    def spark(self):
        '''
            helper method for starting countio effect on interrupt
            data ready signal only appears after data is read 
                -- countio counts edges, if data constantly ready, countio always high, interrupt never triggers
        '''
        for i in range(3):
            temp_g, temp_a = self.gyro, self.acceleration

    """ Imu properties """
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
    
    """ Register Properties """
    # _int1_ctrl  
    @property
    def int1_ctrl(self) -> int:
        return (self._int1_ctrl)

    @int1_ctrl.setter
    def int1_ctrl(self, value: int) -> None:
        self._int1_ctrl = value

    # _ctrl1_xl
    @property
    def int1_ctrl(self) -> int:
        return (self._int1_ctrl)

    @int1_ctrl.setter
    def int1_ctrl(self, value: int) -> None:
        self._int1_ctrl = value
    
    # _ctrl4_c  
    @property
    def ctrl4_c(self) -> int:
        return (self._ctrl4_c)

    @ctrl4_c.setter
    def ctrl4_c(self, value: int) -> None:
        self._ctrl4_c = value

    # _ctrl10_c
    @property
    def ctrl10_c(self) -> int:
        return (self._ctrl10_c)

    @ctrl10_c.setter
    def ctrl10_c(self, value: int) -> None:
        self._ctrl10_c = value
    
    # _master_cfg
    @property
    def master_cfg(self) -> int:
        return (self._master_cfg)

    @master_cfg.setter
    def master_cfg(self, value: int) -> None:
        self._master_cfg = value

    # _tap_cfg    
    @property
    def tap_cfg(self) -> int:
        return (self._tap_cfg)

    @tap_cfg.setter
    def tap_cfg(self, value: int) -> None:
        self._tap_cfg = value
    
    # _tap_ths_6d 
    @property
    def tap_ths_6d(self) -> int:
        return (self._tap_ths_6d)

    @tap_ths_6d.setter
    def tap_ths_6d(self, value: int) -> None:
        self._tap_ths_6d = value
    
    # _int_dur2   
    @property
    def int_dur2(self) -> int:
        return (self._int_dur2)

    @int_dur2.setter
    def int_dur2(self, value: int) -> None:
        self._int_dur2 = value
    
    # _wake_up_ths
    @property
    def wake_up_ths(self) -> int:
        return (self._wake_up_ths)

    @wake_up_ths.setter
    def wake_up_ths(self, value: int) -> None:
        self._wake_up_ths = value

    # _wake_up_dur
    @property
    def wake_up_dur(self) -> int:
        return (self._wake_up_dur)

    @wake_up_dur.setter
    def wake_up_dur(self, value: int) -> None:
        self._wake_up_dur = value

    # _md1_cfg  
    @property
    def md1_cfg(self) -> int:
        return (self._md1_cfg)

    @md1_cfg.setter
    def md1_cfg(self, value: int) -> None:
        self._md1_cfg = value  

    # _sm_ths     
    @property
    def sm_ths(self) -> int:
        return (self._sm_ths)

    @sm_ths.setter
    def sm_ths(self, value: int) -> None:
        self._sm_ths = value    

    