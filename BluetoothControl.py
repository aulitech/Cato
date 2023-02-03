import adafruit_ble

from adafruit_ble.advertising import Advertisement, AdvertisingFlag, AdvertisingFlags

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

        self.advertisement = ProvideServicesAdvertisement( self.hid )
        self.advertisement.appearance = Appearances.hid
        self.advertisement.short_name = "Cato_advert_name"
        # self.advertisement.flags.general_discovery = False
        # self.advertisement.flags.limited_discovery = True
        # self.advertisement.flags.general_discovery = AdvertisingFlag(1)

        self.scan_response = Advertisement(  )
        self.scan_response.short_name = "Cato_scan_resp_name"
        self.scan_response.appearance = Appearances.hid

        
        self.ble = adafruit_ble.BLERadio()
        if self.ble.connected:
            print("Woke up connected")
            for c in self.ble.connections:
                c.disconnect()

        self.battery_service = adafruit_ble.services.standard.BatteryService()
        
        self.k = Keyboard(self.hid.devices)
        self.kl = KeyboardLayoutUS(self.k)
        self.mouse = Mouse(self.hid.devices)

        self.ena_adv = asyncio.Event()
        self.is_connected = asyncio.Event()
        self.is_disconnected = asyncio.Event()

        self.is_disconnected.set() #board starts without connection

        self.tasks = {
            "manage_connection"     : self.manage_connection(),
            "monitor_connections"   : self.monitor_connections(),
            "reconnect"             : self.reconnect()
        }
 
    async def manage_connection(self):
        #print("+ manage_connection")
        while True:
            # wait for advertisement enable
            await self.ena_adv.wait()
            print("BLE_MANAGE: Starting BLE advertisement")
            self.ble.start_advertising(self.advertisement, self.scan_response)
            
            #print(": manage_connection -> is_connected.wait()")
            # wait for a connection
            await self.is_connected.wait()
            self.ena_adv.clear()

            await asyncio.sleep(1)
            self.ble.stop_advertising()
            print("BLE_MANAGE: No longer advertising")
    
    async def reconnect(self):
        #print("+ reconnect")
        while True:
            await self.is_disconnected.wait()
            self.ena_adv.set()
            await asyncio.sleep(5) # rate limit the "start advertising"
            self.ena_adv.clear()
            await asyncio.sleep(0.5) # small advertising reset
        
    async def monitor_connections(self):
        #print("+ monitor_connections")
        while True:
            # Check connection
            if self.ble.connected: # When connected
                if not self.is_connected.is_set():
                    print("BLE_MONITOR: BLE Connected")
                    self.is_connected.set()

                if self.is_disconnected.is_set():
                    self.is_disconnected.clear()
            
            else: # When disconnected

                if not self.is_disconnected.is_set():
                    print("BLE_MONITOR: BLE Disconnected")
                    self.is_disconnected.set()

                if self.is_connected.is_set():
                    self.is_connected.clear()
            await asyncio.sleep(3)