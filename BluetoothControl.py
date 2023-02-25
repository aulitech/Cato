
import adafruit_ble

from adafruit_ble.advertising import Advertisement, AdvertisingFlag, AdvertisingFlags

from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as Keycode
from adafruit_hid.mouse import Mouse

##maybe this should be in a new class file allowing bt services to loaded seperately
from adafruit_ble.uuid import VendorUUID
from adafruit_ble.services import Service
from adafruit_ble.characteristics import Characteristic
from adafruit_ble.characteristics.string import StringCharacteristic

import asyncio

import json

import gc

def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

class Appearances:
    remote = 0x0180 #0x0180 to 0x01BF
    eyeglasses = 0x01C0 #0x01C0 to 0x01FF
    hid = 0x03C0 # 0x03C0 to 0x03FF
    control_device = 0x04C0 # 0x04C0 to 0x04FF

class BluetoothControl(Service):
    uuid = VendorUUID("51ad213f-e568-4e35-84e4-67af89c79ef0")
    
    config = dict
    with open("config.json",'r') as f:
        config = json.load(f)

    configUUID = StringCharacteristic(
        uuid = VendorUUID("e077bdec-f18b-4944-9e9e-8b3a815162b4"),
        properties = Characteristic.READ | Characteristic.WRITE
    )

    # sensors = JSONCharacteristic(
    #     uuid=VendorUUID("528ff74b-fdb8-444c-9c64-3dd5da4135ae"),
    #     properties=Characteristic.READ,
    # )

    def __init__(self):
        super().__init__(service = None)
        
        if(self.config["operation_mode"] >= 20):
            BluetoothControl.cgMessenger = StringCharacteristic(
                uuid = VendorUUID("528ff74b-fdb8-444c-9c64-3dd5da4135ae"),
                properties = Characteristic.READ | Characteristic.WRITE,
            )

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
        self.advertisement.short_name = "Cato"
        # self.advertisement.flags.general_discovery = False
        # self.advertisement.flags.limited_discovery = True
        # self.advertisement.flags.general_discovery = AdvertisingFlag(1)
        # mem("BTC, advertisement created")

        self.scan_response = Advertisement(  )
        self.scan_response.short_name = "Cato"
        self.scan_response.appearance = Appearances.hid
        # mem("BTC, scan_response created")
        
        # BLERadio can toggle advertising state
        self.ble = adafruit_ble.BLERadio()
        
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
            "characteristic_loop"   : self.characteristic_loop(),
            "manage_connection"     : self.manage_connection(),
            "monitor_connections"   : self.monitor_connections(),
            "reconnect"             : self.reconnect()
        }
 
    async def manage_connection(self):
        #print("+ manage_connection")
        while True:
            # First, wait for advertisement enable
            await self.ena_adv.wait()
            print("Bluetooth: Advertising")
            self.ble.start_advertising(self.advertisement, self.scan_response)
            
            # Then, wait for a connection
            await self.is_connected.wait()
            
            # Finally, stop advertising
            self.ena_adv.clear()
            self.ble.stop_advertising()
            print("Bluetooth: Advertising disabled")
    
    async def reconnect(self):
        #print("+ reconnect")
        while True:
            await self.is_disconnected.wait()
            self.ena_adv.set()
            
            await self.is_connected.wait()
            self.ena_adv.clear()
        
    async def monitor_connections(self):
        #print("+ monitor_connections")
        while True:
            # Check connection
            if self.ble.connected: # When connected
                if not self.is_connected.is_set():
                    print("Bluetooth: Connected")
                    self.is_connected.set()

                if self.is_disconnected.is_set():
                    self.is_disconnected.clear()
            
            else: # When disconnected

                if not self.is_disconnected.is_set():
                    print("Bluetooth: Connection Lost")
                    self.is_disconnected.set()

                if self.is_connected.is_set():
                    self.is_connected.clear()
            await asyncio.sleep(3)



    async def characteristic_loop(self):                
        with open("config.json",'r') as f:
            for l in f.readlines():
                self.configUUID = l
                # while(self.configUUID != "NEXT"):
                #     await asyncio.sleep(0.1)
                ##not needed till working interface app
            self.configUUID = "SEND COMPLETE"
        
        ##return not necessary, but offloads control loop imp till finished w collGest
        if(self.config["operation_mode"] >= 20):
            return

        SIGNAL_STRING = {
            "UPDATE"        : self.update_config,
            "OVERWRITE"     : self.overwrite_config
        }
        while(True):
            #replace w event used by control loop
            await asyncio.sleep(1)
            try:
                coro = SIGNAL_STRING[self.configUUID]
            except:
                continue
            await coro()


    async def update_config(self):
        self.configUUID = "READY"
        confBuff = await self._gather_configUUID()
        print(confBuff)
        print(json.loads(confBuff))
        try:
            confBuff = json.loads(confBuff)
        except:
            self.configUUID = "UPDATE ERROR: Invalid Dict"
            return
        
        # k/v pairs WILL update if read before invalid key is reached
        try:
            for k in confBuff.keys():
                self.config[k] = confBuff[k]
        except:
            self.configUUID = "UPDATE ERROR: Invalid Keys"
            return
        
        self.configUUID = "UPDATE COMPLETE"


    async def overwrite_config(self):
        self.configUUID = "READY"
        confBuff = await self._gather_configUUID()
        print(confBuff)

        try:
            confBuff = json.loads(confBuff)
        except:
            self.configUUID = "OVERWRITE ERROR: Invalid Dict"
            return
        
        self.configUUID = "OVERWRITE COMPLETE"


    async def _gather_configUUID(self):
        print("+ _gather_configUUID")
        # rudamentry safety signal in case multiple updates are queued
        self.configUUID = "READY"
        while(self.configUUID == "READY"):
            await asyncio.sleep(0.1)
        
        str = ""
        while(self.configUUID != "COMPLETE"):
            if(self.configUUID != "NEXT"):
                print(": _gather_configUUID\t-> configUUID = ",self.configUUID)
                str += self.configUUID
                self.configUUID = "NEXT"
            await asyncio.sleep(0.1)    ##sleep(0) upon nonhuman uuid interfacing
        print("- _gather_configUUID")
        return str