
import adafruit_ble

from adafruit_ble.advertising import Advertisement#, AdvertisingFlag, AdvertisingFlags

from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as Keycode
from adafruit_hid.mouse import Mouse

from StrUUIDService import SUS
#from ValDict import config
#from StrUUIDService import DebugStream as DBS

import asyncio

import gc

def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

class Appearances:
    remote = 0x0180 #0x0180 to 0x01BF
    eyeglasses = 0x01C0 #0x01C0 to 0x01FF
    hid = 0x03C0 # 0x03C0 to 0x03FF
    control_device = 0x04C0 # 0x04C0 to 0x04FF

class BluetoothControl():

    from ValDict import config
    if(config["HW_UID"] == ""):
        from builtins import hex
        from microcontroller import cpu
        struid = ""
        for b in cpu.uid:
            struid += str(hex(b)[-2:])
        config["HW_UID"] = struid
        import json
        try:
            with open("config.json", 'w') as f:
                json.dump(config, f,sort_keys = True)
        except OSError as oser:
            print("ERROR SAVING UID: "+str(oser))

    if(config["name"] == ""):
        config["name"] = "Cato_" + config["HW_UID"][-6:]
        import json
        try:
            with open("config.json", 'w') as f:
                json.dump(config, f, separators=(",\n"," : "))
        except OSError as oser:
            print("ERROR SAVING NAME: "+str(oser))
    
    # BLERadio can toggle advertising state
    ble = adafruit_ble.BLERadio()
    ble.name = config["name"]

    def __init__(self):
        self.hid = HIDService() # manages human interface device
        print("NEW NAME: ",BluetoothControl.ble.name)
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

        name = BluetoothControl.ble.name
        self.advertisement = ProvideServicesAdvertisement( self.hid )
        self.advertisement.appearance = Appearances.hid
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
        import microcontroller as mc
        self.tasks = {}
        if((BluetoothControl.config["operation_mode"]>=20)or not(mc.nvm[2])):
            self.tasks = {  # tasks
                "characteristic_loop"   : asyncio.create_task(SUS.config_loop()),
                "manage_connection"     : asyncio.create_task(self.manage_connection()),
                "monitor_connections"   : asyncio.create_task(self.monitor_connections()),
                "reconnect"             : asyncio.create_task(self.reconnect())
            }
        
 
    async def manage_connection(self):
        #print("+ manage_connection")
        while True:
            # First, wait for advertisement enable
            await self.ena_adv.wait()
            print("Bluetooth: Advertising")
            BluetoothControl.ble.start_advertising(self.advertisement)

            
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
            print(*self.ble.connections)
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

