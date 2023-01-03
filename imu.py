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

    def __init__(self, i2c_bus: I2C, address: int = LSM6DS_DEFAULT_ADDRESS) -> None:
        super().__init__(i2c_bus, address)

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