# Write your c# SPDX-FileCopyrightText: 2020 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT
# import board

import board
import digitalio
import busio
import sys
import time

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse


import adafruit_ble
from adafruit_ble.advertising import Advertisement
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService

from adafruit_lsm6ds.lsm6ds3trc import LSM6DS3TRC

# On the Seeed XIAO Sense the LSM6DS3TR-C IMU is connected on a separate
# I2C bus and it has its own power pin that we need to enable.
imupwr = digitalio.DigitalInOut(board.IMU_PWR)
imupwr.direction = digitalio.Direction.OUTPUT
imupwr.value = True
time.sleep(0.1)

imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)
sensor = LSM6DS3TRC(imu_i2c)

# Use default HID descriptor
hid = HIDService()
device_info = DeviceInfoService(
    software_revision=adafruit_ble.__version__, manufacturer="AULITECH"
)
advertisement = ProvideServicesAdvertisement(hid)
advertisement.appearance = 961
scan_response = Advertisement()

ble = adafruit_ble.BLERadio()
if ble.connected:
    for c in ble.connections:
        c.disconnect()

print("Waiting for BLE connection")
ble.start_advertising(advertisement, scan_response)

k = Keyboard(hid.devices)
kl = KeyboardLayoutUS(k)
mouse = Mouse(hid.devices)

while True:
    while not ble.connected:
        pass
    print("Connected:")
    ns = 1000
    while ble.connected:
        start = time.monotonic()
        for i in range(0, ns, 1):
            mouse.move(1, 1, 0)
            mouse.move(-1, -1, 0)
        print("Sleeping 10")
        time.sleep(10)
        print("Done sleeping - moving %d samples" % ns)
    ble.start_advertising(advertisement)
