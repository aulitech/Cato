from adafruit_ble.uuid import VendorUUID
from adafruit_ble.services import Service
from adafruit_ble.characteristics import Characteristic
from adafruit_ble.characteristics.string import StringCharacteristic

import microcontroller as mc
import json
import asyncio


config = dict
with open("config.json",'r') as f:
    config = json.load(f)

class StrUUIDService(Service):
    uuid = VendorUUID("51ad213f-e568-4e35-84e4-67af89c79ef0")

    debugUUID = StringCharacteristic(
        uuid = VendorUUID("daba249c-3d15-465e-b0b6-f6162548e137"),
        properties = Characteristic.READ | Characteristic.NOTIFY
    )
    
    collGestUUID = StringCharacteristic(
        uuid = VendorUUID("528ff74b-fdb8-444c-9c64-3dd5da4135ae"),
        properties = Characteristic.READ | Characteristic.NOTIFY | Characteristic.WRITE
    )

    def __init__(self):
        super().__init__(service = None)
        self.connectable = True
    
    async def config_loop(self):
        from Cato import Events as E
        DebugStream.println("+ config_loop")

        SIGNAL_STRING = {
            "REBOOT"        : self.reboot,
            "REBOOTRO"      : self.reboot_forceRO,

            "CG"            : self.collGest_dispatch
        }

        self.collGestUUID = "AWAITING INTERACTION"
        while(True):
            ##test w different time lengths or async event triggers
            await E.gesture_not_collecting.wait()
            await asyncio.sleep(0.2)
            try:
                coro = SIGNAL_STRING[self.collGestUUID]
            except:
                continue
            await coro()
    
    async def reboot(self):
        self.collGestUUID = "REBOOTING"
        mc.reset()
    async def reboot_forceRO(self):
        self.collGestUUID = "REBOOTING READ ONLY"
        mc.nvm[0] = False
        mc.reset()

    async def collGest_dispatch(self):
        from Cato import Events as E
        E.gesture_collecting.set()
        SUS.collGestUUID = "Collect Gestures Dispatched"



# TODO: implement string buffer for larger/delayed inputs and only write once bluetooth is connected
class DebugStream:

    strBuff = ""

    def print(*args, end = ''):
        for a in args:
            DebugStream.strBuff += str(a)
        DebugStream.strBuff += end
        
        print(DebugStream.strBuff, end="")
        while(len(DebugStream.strBuff) > 512):
            SUS.debugUUID = DebugStream.strBuff[:512]
            DebugStream.strBuff = DebugStream.strBuff[512:]
        SUS.debugUUID = DebugStream.strBuff
        DebugStream.strBuff = ""
    
    def println(*args):
        DebugStream.print(*args, end = '\n')

SUS = StrUUIDService()