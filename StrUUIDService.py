from adafruit_ble.services import Service

import microcontroller as mc
import asyncio

from utils import config

class StrUUIDService(Service):
    from adafruit_ble.uuid import VendorUUID
    from adafruit_ble.characteristics.string import StringCharacteristic as SC

    uuid = VendorUUID("51ad213f-e568-4e35-84e4-67af89c79ef0")

    configUUID = SC(
        uuid = uuid,
        properties = SC.READ | SC.NOTIFY | SC.WRITE
    )

    debugUUID = SC(
        uuid = VendorUUID("daba249c-3d15-465e-b0b6-f6162548e137"),
        properties = SC.READ | SC.NOTIFY
    )
    
    devUUID = None
    if("dev" in config["operation_mode"]):
        devUUID = SC(
            uuid = VendorUUID("528ff74b-fdb8-444c-9c64-3dd5da4135ae"),
            properties = SC.READ | SC.NOTIFY | SC.WRITE
        )

    def __init__(self):
        super().__init__(service = None)
        self.connectable = True
    
    async def config_loop(self):
        DebugStream.println("+ characteristic_loop")
    
        SIGNAL_STRING = {
            "SEND"          : self.send_config,
            "UPDATE"        : self.update_config,
            "OVERWRITE"     : self.overwrite_config,
            "SAVE"          : self.save_config,
    
            "CALIBRATE"     : self.calibrate_imu,
            "FULL_CALIBRATE": self.full_calibrate_imu,
            
            "REBOOT"        : self.reboot,
            "REBOOTRO"      : self.reboot_forceRO,
            "BOOTLOADER"    : self.reboot_bootloader,
    
            "DELTAS"        : self.imu_idle_deltas,     # dev handle for checking calibration stats
        }
    
        self.configUUID = "AWAITING INTERACTION"
        while(True):
            ##test w different time lengths or async event triggers
            await asyncio.sleep(0.2)
            try:
                coro = SIGNAL_STRING[self.configUUID]
            except:
                continue
            await coro()


    async def send_config(self):
        l = str(config.d)
        while(len(l) > 512):
            SUS.configUUID = l[:512]
            l = l[512:]
            while(self.configUUID != "NEXT"):
                await asyncio.sleep(0)
        self.configUUID = "SEND COMPLETE"
        return

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
    
        try:
            confBuff = json.loads(confBuff)
        except:
            self.configUUID = "OVERWRITE ERROR: Invalid Dict"
            return
        
        self.configUUID = "OVERWRITE COMPLETE"

    async def _gather_configUUID(self):
        # rudamentry safety signal in case multiple updates are queued
        self.configUUID = "READY"
        while(self.configUUID == "READY"):
            await asyncio.sleep(0.1)
        
        str = ""
        while(self.configUUID != "COMPLETE"):
            if(self.configUUID != "NEXT"):
                str += self.configUUID
                self.configUUID = "NEXT"
            await asyncio.sleep(0.1)    ##sleep(0) upon nonhuman uuid interfacing
        return str

    async def save_config(self):
        self.configUUID = "SAVE NON-OPERATIONAL"
        return
        self.configUUID = "SAVING"
        def repacker():
            return
        try:
            with open("config.json",'w'):
                pass
            temp_dict = {}
            # config.dump()
            self.configUUID = "SAVE COMPLETE"
        except OSError as oser:
            self.configUUID = "SAVE ERROR: "+str(oser)

    async def calibrate_imu(self):
        from Cato import Cato # TODO: Add calibrate to Events, calibrate at top of control loop iff CalibrateEvent is set
        await Cato.imu.calibrate(100)
        self.configUUID = "CALIBRATION COMPLETE"

    async def full_calibrate_imu(self):
        from Cato import Cato
        await Cato.imu.full_calibrate(100)
        self.configUUID = "CALIBRATION COMPLETE"

    async def reboot(self):
        await self.save_config()
        self.configUUID = "REBOOTING"
        mc.reset()

    async def reboot_forceRO(self):
        await self.save_config()
        self.configUUID = "REBOOTING READ ONLY"
        mc.nvm[0] = False
        mc.reset()

    async def reboot_bootloader(self):
        await self.save_config()
        self.configUUID = "RESETTING IN BOOTLOADER"
        mc.on_next_reset(mc.RunMode.UF2)
        mc.reset()

    # currently unused in active models
    async def collGest_dispatch(self):
        from Cato import Events as E
        if(E.gesture_not_collecting.is_set()):
            E.gesture_collecting.set()
            SUS.configUUID = "Collect Gestures Dispatched"
        else:
            SUS.configUUID = "Gesture Collection Already In Progress"

    async def imu_idle_deltas(self):
        from math import sqrt
        from Cato import Cato
        imu = Cato.imu
    
        samples = 50
        iters = 20
        maxDelta = 2
        minMags = [maxDelta]*iters
        maxMags = [0]*iters
        ranges = []
        for i in range(maxDelta*10 +1):
            ranges.append(i/10)
        buckets = [0]*(maxDelta*10 +1)
    
        for i in range(iters):
            await imu.wait()
            initial = [imu.gx,imu.gy,imu.gz]
            s = 0
            while(s < samples):
                await imu.wait()
                delta = [imu.gx,imu.gy,imu.gz]
                mag = 0
                for d in range(len(delta)):
                    delta[d] = abs(initial[d] - delta[d])
                    #buckets[i][int(delta[i]*10)] += 1
                    mag += delta[d]**2
                mag = sqrt(mag)
                
                if(mag >= maxDelta):
                    buckets[-1] += 1
                else:
                    buckets[int(mag*10)] += 1
                
                if(mag < minMags[i]):
                    minMags[i] = mag
                if(mag > maxMags[i]):
                    maxMags[i] = mag
                
                s += 1
        
        print(",\t".join(str(v) for v in ranges))
        print(",\t".join(str(v) for v in buckets))
        print(maxMags)
    
        self.configUUID = str(max(minMags))
        self.configUUID = str(min(maxMags))
        self.configUUID = "IDLE DELTAS COMPUTED"


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