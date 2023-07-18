'''
Cato.py
auli.tech software to drive the Cato gesture Mouse
Written by Finn Biggs finn@auli.tech
    15-Sept-22
'''
import microcontroller as mc

import os

import array

from imu import LSM6DS3TRC

import asyncio

import gc
from BluetoothControl import BluetoothControl

from StrUUIDService import config, DebugStream, SUS

class Events:
    gesture_collecting      = asyncio.Event()   # signal that collect_gestures() is currently running
    gesture_not_collecting  = asyncio.Event()
    gesture_not_collecting.set()

gesture_key = [
    "none",
    "up",
    "down",
    "right",
    "left"
]

class Cato:
    ''' Main Class of Cato Gesture Mouse '''
    imu = LSM6DS3TRC()

    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        DebugStream.println("Cato init: start")

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish
        self.blue = BluetoothControl()

        self.tasks = {
            "test_loop"         : asyncio.create_task(self.test_loop()),
            "collect_gestures"  : asyncio.create_task(Cato.collect_gestures_control())
        }

        self.tasks.update(Cato.imu.tasks)   # functions for t1he imu
        self.tasks.update(self.blue.tasks)  # functions for bluetooth
    
    @property
    def gx(self):
        return Cato.imu.gx
    
    @property
    def gy(self):
        return Cato.imu.gy

    @property
    def gz(self):
        return Cato.imu.gz

    @property
    def ax(self):
        return Cato.imu.ax

    @property
    def ay(self):
        return Cato.imu.ay

    @property
    def az(self):
        return Cato.imu.az

    async def collect_gestures_control():
        from StrUUIDService import SUS
        
        mc.nvm[2] = 0
        Events.gesture_not_collecting.set()
        while(True):
            await Events.gesture_collecting.wait()
            Events.gesture_not_collecting.clear()

            # record five of each gesture in random order
            to_train = list(range(1,len(gesture_key)))
            Cato.shuffle(to_train)
            DebugStream.println(to_train)

            logName = f"log{mc.nvm[2]}.txt"

            await Cato.collect_gestures(to_train=to_train, logName=logName)
            
            if(SUS.cgUUID == "Gesture Collection Completed"):
                mc.nvm[2] += 1
            
            Events.gesture_collecting.clear()
            Events.gesture_not_collecting.set()

    def imu_out(gestID):
        return (Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID)
    
    def mag():
        return (Cato.imu.gx)**2 + (Cato.imu.gy)**2 + (Cato.imu.gz)**2

    async def collect_gestures(to_train     = range(1,len(gesture_key)), 
                               n            = 5, 
                               logName      = "log.txt", 
                               gestLen      = config["gesture_length"], 
                               idleLen      = config["gesture_idle_cutoff"],
                               gestThresh   = config["gesture_movement_threshold"], 
                               idleThresh   = config["gesture_idle_threshold"] 
    ):
        DebugStream.println("+ collect_gestures")
        try:
            with open(logName, 'w') as log:
                pass
        except Exception as e:
            DebugStream.println("Err in CG - couldn't open log.txt")

        if( isinstance(to_train, int) ):
            to_train = (to_train,)
        
        if(mc.nvm[1]):
            SUS.cgUUID = "WARNING: Cato did not boot selfwritable.  Values will not be recorded"
            DebugStream.println("WARNING: Cato did not boot selfwritable.  Values will not be recorded")

        await asyncio.sleep(3)

        SUS.cgUUID = "Begin GC"
        DebugStream.println(SUS.cgUUID)
        
        i = 0
        while(i < n):
            i += 1
            Cato.shuffle(to_train)
            j = 0
            while(j < len(to_train)):
                gestID = to_train[j]
                backlog = []
                mag = 0
                curr_id_msg = f"{gesture_key[gestID]} ({str(gestID)})"
                SUS.cgUUID = curr_id_msg

                # enforce idle start condn
                idle = 0
                while(idle < idleLen):
                    await Cato.imu.wait()
                    mag = Cato.mag()
                    if(mag < gestThresh):
                        idle += 1
                    else:
                        idle = 0
                    backlog.append( Cato.imu_out(0) )
                
                curr_id_msg = f"Do {gesture_key[gestID]} ({str(gestID)})"
                DebugStream.println(curr_id_msg)
                SUS.cgUUID = curr_id_msg

                # wait to recieve significant motion
                cycles = 0
                while (mag < gestThresh):
                    cycles = (cycles + 1) % 100
                    if cycles > 100:
                        backlog.pop(0)
                    await Cato.imu.wait()
                    backlog.append( Cato.imu_out(0) )
                    mag = Cato.mag()

                SUS.cgUUID = "RECORDING"

                ### gesture motion recorded and id'd ###
                idle = 0
                curr_len = 0

                # Record a single gesture until idle
                while (idle < idleLen) and (curr_len < gestLen):
                    await Cato.imu.wait()
                    curr_len += 1

                    backlog.append( Cato.imu_out(gestID) )
                    mag = Cato.mag()

                    if(mag < idleThresh):
                        idle += 1
                    else:
                        idle = 0
                # hold still when you're done, you gremlin - don't break my code
                # enforce idle end condn
                idle = 0
                cycles = 0
                while(idle < idleLen) and (cycles < 100):
                    cycles += 1
                    await Cato.imu.wait()
                    mag = Cato.mag()
                    if(mag < gestThresh):
                        idle += 1
                    else:
                        idle = 0
                    backlog.append( Cato.imu_out(0) )
                
                curr_id_msg = f"Curr Len : {curr_len}"
                SUS.cgUUID = curr_id_msg
                DebugStream.println(SUS.cgUUID)

                # write to log.txt - recording
                curr_id_msg = "Keep this input?(y/n)"
                DebugStream.println(curr_id_msg)
                SUS.cgUUID = curr_id_msg
                while(SUS.cgUUID not in "YyNnQqSs"):
                    await asyncio.sleep(0.1)
                
                if(SUS.cgUUID in "Yy"):
                    # write to local log file
                    try:
                        with open(logName, 'a') as log:
                            SUS.cgUUID = "Logging gesture to " + logName
                            DebugStream.println("Writing to ", logName)
                            for d in backlog:
                                log.write(",".join(str(v) for v in d))
                                log.write("\n")
                    except OSError as oser:
                        SUS.cgUUID = "Gestures cannot be logged"
                        SUS.cgUUID = str(oser)

                elif(SUS.cgUUID in "Nn"):
                    SUS.cgUUID = "Rerecording Gesture"
                    j -= 1

                elif(SUS.cgUUID in "Ss"):
                    SUS.cgUUID = "Recording Skipped"

                elif(SUS.cgUUID in "Qq"):
                    SUS.cgUUID = "Session Canceled"
                    os.remove(logName)
                    return
                
                j += 1
    
        SUS.cgUUID = "Gesture Collection Completed"
        DebugStream.println("Gesture Collection Completed")
        return

    async def stopwatch(n : float,ev : asyncio.Event = None):
        if(n >= 0):
            await asyncio.sleep(n)
            if(ev is not None):
                ev.set()
    
    def shuffle(l : list):
        from random import randint
        for i in range(0,len(l)):
            r = randint(i,len(l)-1)
            if(i != r):
                l[i],l[r] = l[r],l[i]
        return

    async def test_loop(self):
        DebugStream.println("+ test_loop")
        #await self.blue.is_connected.wait()
        i = 0
        # t = asyncio.create_task(Cato.stopwatch(10))

        while(True):
            await Events.gesture_not_collecting.wait()
            i += 1
            DebugStream.println("looping: ",(Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz))
            #DebugStream.println(self.blue.mouse.report)
            await asyncio.sleep(10)
