

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
   
    configUUID = StringCharacteristic(
        uuid = uuid,
        properties = Characteristic.READ | Characteristic.NOTIFY | Characteristic.WRITE
    )

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
        DebugStream.println("+ characteristic_loop")
        with open("config.json",'r') as f:
            for l in f.readlines():
                self.configUUID = l
                # while(self.configUUID != "NEXT"):
                #     await asyncio.sleep(0.1)
                ##not needed till working interface app
            self.configUUID = "SEND COMPLETE"
        
        ##return not necessary, but offloads control loop impl till finished w collGest 
        if(config["operation_mode"] >= 20):
            return

        SIGNAL_STRING = {
            "UPDATE"        : self.update_config,
            "OVERWRITE"     : self.overwrite_config,
            "SAVE"          : self.save_config,

            "REBOOT"        : self.reboot,
            "REBOOTRO"      : self.reboot_forceRO,

            "CG"            : self.collGest_control
        }
        while(True):
            ##test w different time lengths or async event triggers
            await asyncio.sleep(0.2)
            try:
                coro = SIGNAL_STRING[self.configUUID]
            except:
                continue
            await coro()
            ##code to update config.json goes here

    async def update_config(self):
        self.configUUID = "READY"
        confBuff = await self._gather_configUUID()
        DebugStream.println(confBuff)
        DebugStream.println(json.loads(confBuff))
        try:
            confBuff = json.loads(confBuff)
        except:
            self.configUUID = "UPDATE ERROR: Invalid Dict"
            return
        
        # k/v pairs WILL update if read before invalid key is reached
        try:
            for k in confBuff.keys():
                config[k] = confBuff[k]
        except:
            self.configUUID = "UPDATE ERROR: Invalid Keys"
            return
        
        self.configUUID = "UPDATE COMPLETE"

    async def overwrite_config(self):
        self.configUUID = "READY"
        confBuff = await self._gather_configUUID()
        DebugStream.println(confBuff)

        try:
            confBuff = json.loads(confBuff)
        except:
            self.configUUID = "OVERWRITE ERROR: Invalid Dict"
            return
        
        self.configUUID = "OVERWRITE COMPLETE"

    async def _gather_configUUID(self):
        DebugStream.println("+ _gather_configUUID")
        # rudamentry safety signal in case multiple updates are queued
        self.configUUID = "READY"
        while(self.configUUID == "READY"):
            await asyncio.sleep(0.1)
        
        str = ""
        while(self.configUUID != "COMPLETE"):
            if(self.configUUID != "NEXT"):
                DebugStream.println(": _gather_configUUID\t-> configUUID = ",self.configUUID)
                str += self.configUUID
                self.configUUID = "NEXT"
            await asyncio.sleep(0.1)    ##sleep(0) upon nonhuman uuid interfacing
        DebugStream.println("- _gather_configUUID")
        return str
    
    async def save_config(self):
        self.configUUID = "SAVING"
        #testDict = {"testStr" : "Hello World", "testInt" : 23, "testClass" : DebugStream}
        try:
            with open("config.json", 'w') as f:
                json.dump(config, f)    #for some reason "indent" kwarg is not recognized
                ##json formatter method would be nice here to make config.json human readable
            self.configUUID = "SAVE COMPLETE"
        except OSError as oser:
            self.configUUID = "SAVE ERROR: "+str(oser)
    
    async def reboot(self):
        await self.save_config()
        self.configUUID = "REBOOTING"
        mc.reset()
    async def reboot_forceRO(self):
        await self.save_config()
        self.configUUID = "REBOOTING READ ONLY"
        mc.nvm[0] = False
        mc.reset()
    

    async def collGest_control(self):
        from Cato import Events as E
        await E.gesture_not_collecting.wait()
        E.gesture_collecting.set()


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