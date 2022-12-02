import adafruit_ble
from adafruit_ble.advertising import Advertisement
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as Keycode
from adafruit_hid.mouse import Mouse

import asyncio

class Appearances:
    remote = 0x0180 #0x0180 to 0x01BF
    eyeglasses = 0x01C0 #0x01C0 to 0x01FF
    hid = 0x03C0 # 0x03C0 to 0x03FF
    control_device = 0x04C0 # 0x04C0 to 0x04FF

class BluetoothControl:
    def __init__(self):
        self.hid = HIDService()

        self.device_info = DeviceInfoService(
            manufacturer = "AULITECH",
            # github will manage
            # on commit, how is a piece of your code updated
            # can set up new repo to play with - google "how to do revision control in github"
            software_revision = adafruit_ble.__version__, # This is the Cato version
            model_number = None,  # our model number can be "Cato 1"
            serial_number = None, # look on nrf52840 for hardware serial - can ask on Seeed forum - anything unique per board
            firmware_revision = "v0.0",
            hardware_revision = "v0.0",
            service = None
        )

        self.advertisement = ProvideServicesAdvertisement(self.hid)
        self.advertisement.appearance = Appearances.hid
        self.scan_response = Advertisement()
        self.ble = adafruit_ble.BLERadio()
        if self.ble.connected:
            print("Woke up connected")
            for c in self.ble.connections:
                c.disconnect()

        self.battery_service = adafruit_ble.services.standard.BatteryService()
        
        self.k = Keyboard(self.hid.devices)
        self.kl = KeyboardLayoutUS(self.k)
        self.mouse = Mouse(self.hid.devices)
        
    def connect_bluetooth(self):
        self.advertisement = ProvideServicesAdvertisement(self.hid)
        print("Waiting for BLE connection")
        self.ble.start_advertising(self.advertisement, self.scan_response)
        # multiple connections occur here
        # device powers up -> how do we connect to multiple devices
        # "conenction is triggered from far end" -> when we advertise, if there are 2 devices that know us, both will try to connect
        while not self.ble.connected:
            #we will need to increase granularity
            pass
        print("    Connected")


