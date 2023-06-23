'''
Cato.py
auli.tech software to drive the Cato gesture Mouse
Written by Finn Biggs finn@auli.tech
    15-Sept-22
'''
import sys
import board
import microcontroller as mc

import busio
import os
import io
import json
import time
import digitalio
import countio
import alarm

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse

from math import sqrt, atan2, sin, cos, pow, pi
import array
import supervisor as sp

from battery import Battery
from imu import LSM6DS3TRC

import asyncio

import gc

from neutonml import Neuton

from StrUUIDService import config
from StrUUIDService import DebugStream


#helpers and enums

class ST():
    '''enum states'''
    IDLE = 0
    MOUSE_BUTTONS = 1
    KEYBOARD = 2


class EV(): #these are actually gestures
    gesture_key = [
        "None",
        "Nod Up",
        "Nod Down",
        "Nod Right",
        "Nod Left",
        "Tilt Right",
        "Tilt Left",
        "Shake Vertical",
        "Shake Horizontal",
        "Circle Clockwise",
        "Circle Counterclockwise"
    ]
    ''' enum events '''
    NONE = 0
    UP = 1
    DOWN = 2
    RIGHT = 3
    LEFT = 4
    ROLL_R = 5
    ROLL_L = 6
    SHAKE_YES = 7
    SHAKE_NO = 8,
    CIRCLE_CW = 9,
    CIRCLE_CCW = 10

class Events:
    control_loop            = asyncio.Event()   # enable flow through main control loop - set this in detect event
    move_mouse              = asyncio.Event()   # move the mouse
    mouse_done              = asyncio.Event()   # indicates mouse movement has finished
    scroll                  = asyncio.Event()   # scroll the screen
    scroll_done             = asyncio.Event()   # indicates scroll has finished
    scroll_lr               = asyncio.Event()   # scroll left to right
    scroll_lr_done          = asyncio.Event()   # indicates that scroll_lr has completed
    wait_for_motion         = asyncio.Event()   # wait_for_motion
    wait_for_motion_done    = asyncio.Event()   # wait-for-motion exit indicator
    sig_motion              = asyncio.Event()   # indicates that there has been significant motion during wait_for_motion's window
    stream_imu              = asyncio.Event()   # stream data from the imu onto console -- useful for debugging
    mouse_event             = asyncio.Event()   # triggers detection of Cato gesture
    idle                    = asyncio.Event()   # triggered when no events change for some time

    gesture_collecting      = asyncio.Event()   # signal that collect_gestures() is currently running
    gesture_not_collecting  = asyncio.Event()
    gesture_not_collecting.set()

# I can't make the "Neuton: Constructing buffer from ... go away unless I crack open the circuitpython uf2"
neuton_outputs = array.array( "f", [0, 0, 0, 0, 0, 0, 0, 0] )

def mem( loc = "" ):
    DebugStream.println(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

class Cato:

    ''' Main Class of Cato Gesture Mouse '''
    imu = LSM6DS3TRC()
    n = Neuton(outputs=neuton_outputs)

    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        DebugStream.println("Cato init: start")

        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        
        #DebugStream.println(config)
        mode = config["operation_mode"]
        if(mode >=20)&(bool(mc.nvm[0])):
            DebugStream.println("WARNING: Collect Gesture mode will not record data")

        #specification for operation
        self.specs = {
            "freq" : 104.0, # imu measurement frequency (hz)
            "g_dur": 0.75   # gesture duration (s)
        }

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish

        # battery managing container
        self.battery = Battery()

        self.blue = BluetoothControl.BluetoothControl()

        self.state = ST.IDLE
        if(mode < len(config["st_matrix"])):
            self.st_matrix = config["st_matrix"][mode]

        # Mode-dependent task spawning
        """ MODE CODE MEANINGS
                0 - 9: USER MODES
                    0:  Default Computer
                    1:  Default Television
                    2:  Forever Pointer (only pointer)
                    3:  Forever Clicker (only clicker - tap detect)
                10 - 19: Dev Test Modes:
                    10: Test Loop -- bluetooth print test
                20 - 29: Gesture Collection Modes
                    20: Collect Gestures
                    2#: Collect Gesture Number #
                30 - 39: Unused
                    30: There's nothing here
                    31: Really, nothing
        """

        self.tasks = {
            "test_loop"         : asyncio.create_task(self.test_loop()),
            "collect_gestures"  : asyncio.create_task(Cato.collect_gestures_control())
        }
        #DebugStream.println("neuton ",Cato.n.window_size)
        
        self.tasks.update(Cato.imu.tasks)   # functions for t1he imu
        self.tasks.update(self.blue.tasks)  # functions for bluetooth

        self.gesture = EV.NONE
    
    async def reboot():
        mc.reset()


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
    
    async def monitor_battery(self):
        while True:
            await asyncio.sleep(3)
            temp = self.battery.raw_value
            # DebugStream.println(f"bat_ena True: {temp[0]}")
            await asyncio.sleep(0.1)
            # uDebugStream.println(f"bat_ena False: {temp[1]}")
            self.blue.battery_service.level = self.battery.level

    async def collect_gestures_control():
        from StrUUIDService import SUS
        
        mc.nvm[2] = 0
        Events.gesture_not_collecting.set()
        while(True):
            await Events.gesture_collecting.wait()
            Events.gesture_not_collecting.clear()

            # record five of each gesture in random order
            to_train = list(range(1,len(EV.gesture_key)))
            Cato.shuffle(to_train)
            DebugStream.println(to_train)
            n = 5
            logName = f"log{mc.nvm[2]:2}.txt"

            await Cato.collect_gestures(to_train=to_train,n=n,logName=logName)

            
            if(SUS.collGestUUID == "Gesture Collection Completed"):
                mc.nvm[2] += 1
            
            Events.gesture_collecting.clear()
            Events.gesture_not_collecting.set()
    
    async def collect_gestures(to_train = range(1,len(EV.gesture_key)), n = 10, logName = "log.txt", gestLen = 5):
        from StrUUIDService import SUS

        DebugStream.println("+ collect_gestures")
        try:
            with open(logName, 'w') as log:
                pass
        except:
            pass

        if(isinstance(to_train,int)):
            to_train = (to_train,)
        
        if(mc.nvm[1]):
            SUS.collGestUUID = "WARNING: Cato did not boot selfwritable.  Values will not be recorded"
            DebugStream.println("WARNING: Cato did not boot selfwritable.  Values will not be recorded")

        await asyncio.sleep(3)

        gest_timer = asyncio.Event()
        SUS.collGestUUID = "Collecting Gestures"
        DebugStream.println(SUS.collGestUUID)
        #try:
        for gestID in to_train:
            #SUS.collGestUUID = "Gesture: "+EV.gesture_key[gestID]+"("+str(gestID)+")"
            i = 0
            while(i < n):
                i += 1
                hist = []
                maxGest = []
                maxMag = 0

                SUS.collGestUUID = EV.gesture_key[gestID]+"("+str(gestID)+")"
                while(SUS.collGestUUID == EV.gesture_key[gestID]+"("+str(gestID)+")"):
                    await asyncio.sleep(0.1)

                while(len(hist) < gestLen):
                    await Cato.imu.wait()
                    hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
                    maxGest.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
                
                delta = []
                for col in range(0,len(hist[0])-1):
                    delta.append(hist[gestLen//2][col] - hist[gestLen//2 -1][col])
                maxMag = (delta[3])**2 + (delta[4])**2 + (delta[5])**2
                
                SUS.collGestUUID = str(maxMag)
                asyncio.create_task(Cato.stopwatch(3, ev = gest_timer))  # Timer starts here
                DebugStream.println("Perform Gesture: ", EV.gesture_key[gestID])
                SUS.collGestUUID = "Perform Gesture ("+str(i)+")"

                while(not gest_timer.is_set()):
                    await Cato.imu.wait()
                    hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
                    hist.pop(0)

                    delta = []
                    for col in range(0,len(hist[0])-1):
                        delta.append(hist[gestLen//2][col] - hist[gestLen//2 -1][col])
                    currMag = (delta[3])**2 + (delta[4])**2 + (delta[5])**2

                    if(currMag > maxMag):
                        DebugStream.println("New Max Read")
                        DebugStream.println(currMag, ">", maxMag)
                        maxMag = currMag
                        maxGest = hist.copy()
                        
                gest_timer.clear()
                DebugStream.println("recording length: "+str(len(maxGest)))
                # record data
                SUS.collGestUUID = "Keep this input?(y/n)"
                while(SUS.collGestUUID not in ('Y','y','N','n','Q','q','S','s')):
                    await asyncio.sleep(0.1)
                if(SUS.collGestUUID in ('Y','y')):
                    ''''''
                    # write to local log until app is functional
                    try:
                        with open(logName, 'a') as log:
                            SUS.collGestUUID = "Logging gesture to "+logName
                            DebugStream.println("Writing to",logName)
                            for d in maxGest:
                                log.write(",".join(str(v) for v in d))
                                log.write("\n")
                    except OSError as oser:
                        SUS.collGestUUID = "Gestures cannot be logged"
                        SUS.collGestUUID = str(oser)
                        continue
                    
                elif(SUS.collGestUUID in ('N','n')):
                    SUS.collGestUUID = "Rerecording Gesture"
                    i -= 1
                elif(SUS.collGestUUID in ('Q','q')):
                    SUS.collGestUUID = "Session Canceled"
                    os.remove(logName)
                    return
                else:
                    SUS.collGestUUID = "Recording Skipped"

            SUS.collGestUUID = "Finished Recordings of " + EV.gesture_key[gestID]
    
        SUS.collGestUUID = "Gesture Collection Completed"
        DebugStream.println("Gesture Collection Completed")
        '''
        except Exception as er:
            SUS.collGestUUID = "An Error Ocurred Durring Gesture Collection"
            DebugStream.println(er)
        '''

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
        t = asyncio.create_task(Cato.stopwatch(10))

        while(True):
            await Events.gesture_not_collecting.wait()
            #DebugStream.println("loop: ",i)
            #DebugStream.println(t.done())
            i += 1
            DebugStream.println(self.gx,', ',Cato.imu.gx)
            await asyncio.sleep(5)
