
import adafruit_ble

from adafruit_ble.advertising import Advertisement, AdvertisingFlag, AdvertisingFlags

from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService
from adafruit_ble.services.nordic import UARTService

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as Keycode
from adafruit_hid.mouse import Mouse

from StrCharacteristicService import SCS
from StrCharacteristicService import config
from StrCharacteristicService import StrCharacteristicService
from StrCharacteristicService import DebugStream
## maybe this should be in a new class file allowing bt services to loaded seperately

import asyncio

import json

import gc

def mem( loc = "" ):
    DebugStream.print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

class Appearances:
    remote = 0x0180 #0x0180 to 0x01BF
    eyeglasses = 0x01C0 #0x01C0 to 0x01FF
    hid = 0x03C0 # 0x03C0 to 0x03FF
    control_device = 0x04C0 # 0x04C0 to 0x04FF

class BluetoothControl():
    # BLERadio can toggle advertising state
    ble = adafruit_ble.BLERadio()

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
        name = "Cato_Remote_Glasses"
        self.advertisement = ProvideServicesAdvertisement( self.hid )
        self.advertisement.appearance = Appearances.remote
        self.advertisement.short_name = name
        # self.advertisement.flags.general_discovery = False
        # self.advertisement.flags.limited_discovery = True
        # self.advertisement.flags.general_discovery = AdvertisingFlag(1)
        # mem("BTC, advertisement created")

        self.scan_response = Advertisement(  )
        self.scan_response.short_name = name
        self.scan_response.appearance = Appearances.remote
        # # mem("BTC, scan_response created")
        
        
        # HID handles
        self.k = Keyboard(self.hid.devices)
        self.kl = KeyboardLayoutUS(self.k)
        self.mouse = Mouse(self.hid.devices)
        
        # Battery service. Can inform central of battery level with this.level
        self.battery_service = adafruit_ble.services.standard.BatteryService()

        self.ena_adv = asyncio.Event()          # enable advertising
        self.is_connected = asyncio.Event()     # indicates connection
        self.is_disconnected = asyncio.Event()  # indicates disconnection

        self.is_disconnected.set() #board starts without connection

        self.tasks = {  # tasks
            "characteristic_loop"   : asyncio.create_task(SCS.config_loop()),
            "manage_connection"     : asyncio.create_task(self.manage_connection()),
            "monitor_connections"   : asyncio.create_task(self.monitor_connections()),
            "reconnect"             : asyncio.create_task(self.reconnect())
        }
 
    async def manage_connection(self):
        #DebugStream.println("+ manage_connection")
        while True:
            # First, wait for advertisement enable
            await self.ena_adv.wait()
            DebugStream.println("Bluetooth: Advertising")
            BluetoothControl.ble.start_advertising(self.advertisement)
            
            # Then, wait for a connection
            await self.is_connected.wait()
            
            # Finally, stop advertising
            self.ena_adv.clear()
            BluetoothControl.ble.stop_advertising()
            DebugStream.println("Bluetooth: Advertising disabled")
    
    async def reconnect(self):
        #DebugStream.println("+ reconnect")
        while True:
            await self.is_disconnected.wait()
            self.ena_adv.set()
            
            await self.is_connected.wait()
            self.ena_adv.clear()
        
    async def monitor_connections(self):
        #DebugStream.println("+ monitor_connections")
        while True:
            # Check connection
            if BluetoothControl.ble.connected: # When connected
                if not self.is_connected.is_set():
                    DebugStream.println("Bluetooth: Connected")
                    self.is_connected.set()

                if self.is_disconnected.is_set():
                    self.is_disconnected.clear()
            
            else: # When disconnected

                if not self.is_disconnected.is_set():
                    DebugStream.println("Bluetooth: Connection Lost")
                    self.is_disconnected.set()

                if self.is_connected.is_set():
                    self.is_connected.clear()
            await asyncio.sleep(3)