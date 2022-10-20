import adafruit_ble
from adafruit_ble.advertising import Advertisement
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as Keycode
from adafruit_hid.mouse import Mouse

class BluetoothControl:
    def __init__(self):
        self.hid = HIDService()
        self.device_info = DeviceInfoService(
            software_revision=adafruit_ble.__version__, manufacturer="AULITECH",
        )
        self.advertisement = ProvideServicesAdvertisement(self.hid)
        self.advertisement.appearance = 961
        self.scan_response = Advertisement()
        self.ble = adafruit_ble.BLERadio()
        #self.ble.name = "MY_BLUETOOTH_NAME"
        print("BLE NAME:", self.ble.name)
        if self.ble.connected:
            print("Woke up connected")
            for c in self.ble.connections:
                c.disconnect()
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


