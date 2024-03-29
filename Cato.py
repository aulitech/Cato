'''
Cato.py
auli.tech software to drive the Cato gesture Mouse
Written by Finn Biggs finn@auli.tech
    15-Sept-22
'''
import board
import microcontroller as mc

import digitalio
import alarm

from math import sqrt, atan2, sin, cos
from utils import translate, stopwatch, get_mag

import array

from battery import Battery
from imu import LSM6DS3TRC

import asyncio

import gc

from neutonml import Neuton

from utils import config
from utils import pins
from StrUUIDService import DebugStream as DBS
from BluetoothControl import BluetoothControl

from adafruit_hid.keycode import Keycode

from WakeDog import WakeDog

#helpers and enums
EV_NONE = 0
class Events:
    control_loop            = asyncio.Event()   # enable flow through main control loop - set this in detect event
    move_mouse              = asyncio.Event()   # move the mouse
    mouse_idle              = asyncio.Event()   # indicates mouse movement has finished
    mouse_dwell             = asyncio.Event()
    scroll                  = asyncio.Event()   # scroll the screen
    scroll_done             = asyncio.Event()   # indicates scroll has finished
    scroll_lr               = asyncio.Event()   # scroll left to right
    scroll_lr_done          = asyncio.Event()   # indicates that scroll_lr has completed
    sleep                   = asyncio.Event()   # indicates time to go to sleep
    feed_neuton             = asyncio.Event()   # prevent multiple instances of neuton being fed
    sig_motion              = asyncio.Event()   # indicates that there has been significant motion during the movement
    stream_imu              = asyncio.Event()   # stream data from the imu onto console -- useful for debugging
    mouse_event             = asyncio.Event()   # triggers detection of Cato gesture
    gesturing               = asyncio.Event()   # 
    battery                 = asyncio.Event()

    imu_sig_motion          = asyncio.Event()   # code needs refactor using these as primary elements
    imu_idle                = asyncio.Event()

    gesture_collecting      = asyncio.Event()   # signal that collect_gestures() is currently running
    gesture_not_collecting  = asyncio.Event()

    gesture_not_collecting.set()

# Home for neuton inference

neuton_outputs = array.array( "f", [0]*(1 if ('gesture' not in config.keys()) else len(config['gesture']['key'])) )

class Cato:
    ''' Main Class of Cato Gesture Mouse '''

    imu = LSM6DS3TRC()

    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        DBS.println("+ Cato Init")

        if(mc.nvm[2]): # Wired training condn
            mc.nvm[2] = False
            
            self.tasks = {
                "collect_gesture"   : asyncio.create_task(Cato.collect_gestures_app())    
            }
            Events.gesture_collecting.set()
            return

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish

        # battery managing container
        self.battery = Battery()
        
        self.blue = BluetoothControl()

        self.state = 0 # CHOPPING BLOCK??

        mode = config["operation_mode"]
        if "bindings" in config.keys():
            self.bindings = config["bindings"]
        
        self.tasks = {}
        
        if(mode == "gesture_mouse"):
            self.tasks = {
                "move_mouse"        : asyncio.create_task(self.move_mouse()),
                "mouse_event"       : asyncio.create_task(self.mouse_event()),
                "scroll"            : asyncio.create_task(self.scroll())
            }
        elif(mode == "tv_remote"):
            self.tasks = {
                "tv_remote"        : asyncio.create_task(self.tv_control()),
            }
        elif(mode == "pointer"):
            self.tasks = {
                "point"             : asyncio.create_task(self.move_mouse(forever = True)),
            }
            Events.move_mouse.set()
        elif(mode == "clicker"):
            self.tasks = {
                "clicker"           : asyncio.create_task(self.clicker_task()),
            }
        elif(mode == "practice"):
            self.tasks = {
                "gesture_loop"         : asyncio.create_task(self.gesture_practice_loop())
            }
        elif("dev" in mode):
            self.tasks = {
                "test_loop"         : asyncio.create_task(self.test_loop())
            }

        if not mc.nvm[2] and "dev" not in mode:
            self.tasks.update( {
                "monitor_battery"   : asyncio.create_task(self.monitor_battery()),
                "sleep"             : asyncio.create_task(self.go_to_sleep())}
                )
        
        self.tasks.update( Cato.imu.tasks )   # functions for t1he imu
        self.tasks.update( self.blue.tasks )  # functions for bluetooth
        self.tasks.update( WakeDog.tasks )    # functions for waking / sleeping monitoring

        self.n = Neuton(outputs=neuton_outputs)
        self.gesture = 0 # None

        self.pins = pins

        DBS.println("- Cato Init")

    def query_imu_regs(self):
        msg = ""
        msg += f"int1_ctrl:     {(hex)(self.imu.int1_ctrl)}\n"
        msg += f"ctrl1_xl:      {(hex)(self.imu._ctrl1_xl)}\n"
        msg += f"tap_cfg:       {(hex)(self.imu._tap_cfg)}\n"
        msg += f"tap_ths_6d:    {(hex)(self.imu._tap_ths_6d)}\n"
        msg += f"_int_dur2:     {(hex)(self.imu._int_dur2)}\n"
        return msg
    
    async def go_to_sleep(self):
        # This method sets a Cato to go to sleep - presently after exactly 15 seconds, soon to be based on inactivity
        while True:
            # await asyncio.sleep(1) # TAKE IMU READINGS BEFORE TRYING TO GO BACK TO SLEEP?
            await Events.sleep.wait()
            self.tasks['interrupt'].cancel() #release pin int1
            await asyncio.sleep(0.1)
            self.tasks['interrupt'] = None

            self.imu.single_tap_cfg() # set wakeup condn to single tap detection

            pin_alarm = alarm.pin.PinAlarm(pin = board.IMU_INT1, value = True) #Create pin alarm
            
            # ensure that LED is OFF
            for pin in pins.values():
                pin.value = True
            
            import time
            sleep_time = time.time()
            print("LIGHT SLEEP")
            alarm.light_sleep_until_alarms(pin_alarm)
            print("WOKE UP")

            # restart if sleep was long
            if(time.time() - sleep_time > 600):
                mc.reset()

            del(pin_alarm) # release imu_int1
            print("Del pin")

            if(config['operation_mode'] == "clicker"):
                Cato.imu.single_tap_cfg() # set up click task

            else:
                Cato.imu.data_ready_on_int1_setup() #setup imu data ready
                print("Mode other")

            Events.sleep.clear()
            WakeDog.feed()
            
            self.tasks['interrupt'] = asyncio.create_task(self.imu.interrupt())
            self.imu.data_ready.clear()
            self.imu.imu_ready.set()
            
            await asyncio.sleep(0.1)
    
    async def pointer_sleep(self, hall_pass: asyncio.Event = None):
        DBS.println("+ pointer_sleep")
        target = {'command' : '', 'args' : []}
        while(target['command'] != 'pointer_sleep')and(not Events.sleep.is_set()):
            target = await self.gesture_interpreter(timeout = 0)
            DBS.println(target)
        
        hall_pass.set()
        return

    async def monitor_battery(self):
        colors = ['led_red', 'led_green', 'led_blue']
        num_blinks = 1 # number of time to blink each led
        num_iters = 1 # number of times to repeat pattern
        sleep_time = 0.2
        while True:
            try:
                for color in colors:
                    for i in range(num_blinks):
                        pins[color].value = False
                        await asyncio.sleep(sleep_time)
                        pins[color].value = True
                        #await asyncio.sleep(sleep_time)
                    
            except:
                pass

            batt_timer = 10
            await asyncio.sleep(batt_timer)

            # print("monitor_battery")
            self.blue.battery_service.level = self.battery.level

    async def _move_mouse(self, hall_pass: asyncio.Event = None):
        Events.move_mouse.set()
        await Events.mouse_idle.wait()
        Events.move_mouse.clear()
        Events.mouse_idle.clear()
        hall_pass.set()

    async def center_mouse_cursor(self, hall_pass: asyncio.Event = None):
        x = config["screen_size"]["width"]
        y = config["screen_size"]["height"]
        try:
            self.blue.mouse.move(-2 * x, -2 * y)
            self.blue.mouse.move(int(0.5*x), int(0.5*y))
        except ConnectionError as ce:
            DBS.println("ConnectionError: connection lost in center_mouse_cursor()")
            DBS.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()
    
    async def block_on_eval(self, target: str):
        cmd_str = "self." + target['command']
        arg_str = target['args']
        print(f"Command: {cmd_str}\nArgs: {arg_str}")
        await self.block_on(eval("self."+target['command'], {"self":self}), *target['args'])
    
    async def block_on(self, coro, *args):
        '''
            await target function having uncertain runtime which also needs to use async imu functionality  \n
            coro: Coroutine or other awaitable
        '''
        task = asyncio.create_task(coro( *args, hall_pass=self.hall_pass))
        await self.hall_pass.wait()
        self.hall_pass.clear()
    
    async def mouse_event(self): 
        ''' calls to gesture detection libraries '''
        while True:
            await Events.mouse_event.wait()
            Events.mouse_event.clear()
            await Events.gesture_not_collecting.wait()
            target = await self.gesture_interpreter(indicator = self.shake_cursor)
            print(f"Target: {target}")
            await self.block_on_eval(target)
            print(f"\t \"{target}\" finished at mouse_event")
            
            #DBS.println("Detect Event: Finished Dispatching")
            Events.control_loop.set()
    
    async def tv_control(self):
        Cato.imu.data_ready_on_int1_setup()
        DBS.println("tv_control")
        config["gesture"]["timeout"] = 0
        await_actions = config["tv_remote"]["await_actions"]
        while True:
            await Events.gesture_not_collecting.wait()
            target = await self.gesture_interpreter(timeout = 0)
            DBS.println(target)
            action = asyncio.create_task(self.block_on_eval(target))
            if(await_actions):
                await action
    
    async def gesture_interpreter(self, indicator = None, timeout = (1 if ('gesture' not in config.keys()) else config['gesture']['timeout'])):
        gc.collect()
        # DBS.println("+gesture_interpreter mem: ",gc.mem_free())
        # load interpreter specific parameters
        confThresh  = config["gesture"]["confidence_threshold"]
        maxLen      = config["gesture"]["length"]
        idleLen     = config["gesture"]["idle_cutoff"]
        gestThresh  = config["gesture"]["start_threshold"]
        idleThresh  = config["gesture"]["idle_threshold"]
        
        # counters for in-progress gestures
        length = 1 # number of samples in gesture at present
        mag = 0 # magnitude (squared for now) of gestures gyro movement
        infer = 0 # ID of Neuton's inference
        idle = 0 # Current number of consecutive idle samples

        def gyro_mag():
            return get_mag((Cato.imu.gx,Cato.imu.gy,Cato.imu.gz))

        await Cato.imu.wait()
        mag = gyro_mag()

        # Revenge of the Thrash Window
        if mag > gestThresh:
            return {'command' : 'noop', 'args' : []}
        
        Events.gesturing.set()
        if(indicator != None):
            indicator = asyncio.create_task(indicator())
        
        DBS.println("Perform Gesture Now")
        DBS.println("\tWatching for significant motion...")

        # wait to recieve significant motion and return if the timeout threshold is passed
        timeoutEv = asyncio.Event()
        Events.battery.set()
        asyncio.create_task(stopwatch(timeout, ev = timeoutEv))
        await asyncio.create_task(self.wait_for_motion(gestThresh, terminator = timeoutEv.is_set))
        if(not Events.sig_motion.is_set()):
            Events.gesturing.clear()
            DBS.println("\tTimeout")
            Events.battery.set()
            Events.battery.clear()
            Events.gesturing.clear()
            return self.bindings[EV_NONE]
        Events.battery.clear()
        Events.sig_motion.clear()
        
        # motion recieved
        DBS.println("\tMotion recieved")
        Events.sig_motion.set()
        self.n.set_inputs(
            array.array('f', [Cato.imu.ax, Cato.imu.ay, Cato.imu.az,
                              Cato.imu.gx, Cato.imu.gy, Cato.imu.gz]))

        # feed neuton until idled for 'idleLen' loops
        while(length < maxLen)and(idle < idleLen):
            await Cato.imu.wait()
            data = array.array('f',[Cato.imu.ax, Cato.imu.ay, Cato.imu.az,
                                    Cato.imu.gx, Cato.imu.gy, Cato.imu.gz])
            if(not self.n.set_inputs(data)):
                break
            mag = gyro_mag()
            #DBS.println((Cato.imu.gx,Cato.imu.gy,Cato.imu.gz,mag))
            length += 1

            if(mag**2 < idleThresh):
                idle += 1
            else:
                idle = 0
        # DBS.println("Gesture Length: ",length)
        Events.sig_motion.clear()

        # fill remaining space w 0's
        while(idle == idleLen)and(length < maxLen):
            length += 1
            if(not self.n.set_inputs(array.array('f', [0]*6)))and(length < maxLen):
                DBS.println("WARNING: PREMATURE NEUTON FILL")
                break
        #DBS.println("Filled length: ", length)

        infer = self.n.inference()+1
        # DBS.println(neuton_outputs)
        
        gesture_result_str = f"Result: {config['gesture']['key'][infer]} \n"
        for idx, gesture in enumerate(config['gesture']['key'][1:]):
            gesture_result_str += f"\t{gesture:12}: {neuton_outputs[idx]:>5.1%}\n"
        print(gesture_result_str)
        # DBS.println("Interpreted "+config["gesture"]["key"][infer]+"("+str(max(neuton_outputs))+")")
        Events.battery.set()
        Events.battery.clear()
        Events.gesturing.clear()
        if(indicator != None):
            await indicator
        gc.collect()
        if(max(neuton_outputs) < confThresh):
            return {'command' : 'noop', 'args' : []}     # always perform no operation on failed gesture read
        # DBS.println("-gesture_interpreter mem: ",gc.mem_free())
        return self.bindings[infer]
    
    async def wait_for_motion(self, thresh, terminator = None):
        Events.sig_motion.clear()
        mag = 0
        while(mag < thresh):
            if((terminator != None)and(terminator())):
                return False
            if(Cato.imu.setup_type == "tap"):
                if(Cato.imu.data_ready.is_set()):
                    mag = Cato.imu.tap_type
                await asyncio.sleep(0.05)
            elif(Cato.imu.setup_type == "gyro"):
                await Cato.imu.wait()
                mag = get_mag((Cato.imu.gx,Cato.imu.gy,Cato.imu.gz))
        Events.sig_motion.set()
        return True
    
    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    async def noop(self, hall_pass: asyncio.Event = None):
        ''' no operation '''
        # DBS.println("nooping")
        if hall_pass is not None:
            hall_pass.set()

    # Cato Mouse Actions
    async def shake_cursor(self, hall_pass: asyncio.Event = None):
        mv_size = config['mouse']['shake_size']
        num_wiggles = config['mouse']['num_shake']
        moves = [
            # L R R L (horizontal wiggle)
            (-mv_size,  0,          0),
            (mv_size,   0,          0),
            (mv_size,   0,          0),
            (-mv_size,  0,          0),

            # U D D U (vert wiggle)
            (0,         mv_size,    0),
            (0,         -mv_size,   0),
            (0,         -mv_size,   0),
            (0,         mv_size,    0),
        ]

        displacement = [0,0,0]
        try:
            for wiggle in range(num_wiggles):
                for move in moves:
                    for _ in range(2):
                        await asyncio.sleep(0.02)
                        self.blue.mouse.move( *move )
                        displacement[0] -= move[0]
                        displacement[1] -= move[1]
                        displacement[2] -= move[2]
                    if(not Events.gesturing.is_set()):
                        break
                else: continue
                break
            if(displacement != [0,0,0]):
                self.blue.mouse.move(*displacement)

        except ConnectionError as ce:
            DBS.println("ConnectionError: connection lost in shake_cursor()")
            DBS.println(str(ce))
        
        if hall_pass is not None:
            hall_pass.set()
    
    async def clicker_task(self):
        Cato.imu.single_tap_cfg()
        while True:
            Events.battery.set()
            Events.gesturing.set()
            await Cato.imu.wait()
            Events.sig_motion.set()
            Events.battery.clear()
            WakeDog.feed()
            try:
                target = self.bindings[Cato.imu.tap_type]
                print("In Clicker Task")
                Events.sig_motion.clear()
                Events.gesturing.clear()
                print(target)
                await self.block_on_eval(target)
            except ConnectionError as ce:
                DBS.println("ConnectionError: connection lost in clicker_task()")
                DBS.println(str(ce))

    async def quick_calibrate(self, hall_pass: asyncio.Event = None):
        await asyncio.sleep(0.5)
        await asyncio.create_task(Cato.imu.calibrate(100))
        await asyncio.create_task(self.shake_cursor())
        if hall_pass is not None:
            hall_pass.set()

    async def quick_sleep(self, hall_pass: asyncio.Event = None):
        Events.sleep.set()
        if hall_pass is not None:
            hall_pass.set()

    async def set_state(self, increment, value, hall_pass: asyncio.Event = None):
        self.all_release()
        if(increment):
            self.state += value
        else:
            self.state = value
        numStates = len(self.bindings[0])
        self.state = self.state % numStates
        if hall_pass is not None:
            hall_pass.set()
    
    async def set_dwell(self, bind, hall_pass: asyncio.Event = None):
        # this action is mostly not useful
        if(self.bindings[0] == bind):
            self.bindings[0] = ["noop"]
        else:
            self.bindings[0] = bind
        
        if hall_pass is not None:
            hall_pass.set()

    async def dwell_click(self, buttons, tiltThresh, hall_pass: asyncio.Event = None):
        async def tilt_check():
            await Cato.imu.wait()
            while(not (abs(Cato.imu.gx) > max(sqrt(Cato.imu.gy**2+Cato.imu.gz**2), tiltThresh))):
                await Cato.imu.wait()
            DBS.println("Tilted!!")
            return

        async def dwell_clicker(buttons: int):
            await Events.mouse_dwell.wait()
            Events.mouse_dwell.clear()
            while(True):
                DBS.println("Clicked: ",buttons)
                self.blue.mouse.click(buttons)
                await Events.mouse_dwell.wait()
                Events.mouse_dwell.clear()

        tcTask = asyncio.create_task(tilt_check())
        clicker = None
        if(buttons):
            clicker = asyncio.create_task(dwell_clicker(buttons))
        Events.move_mouse.set()

        await tcTask
        if(clicker != None):
            clicker.cancel()
        Events.move_mouse.clear()
        DBS.println("-dwell_click")

        if hall_pass is not None:
            hall_pass.set()
        return


    async def move_mouse(self, mouse_type = "ACCEL", forever: bool = False):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''
        # mem("move_mouse -- pre settings load")

        idle_thresh = config['mouse']['idle_threshold'] # speed below which is considered idle  
        min_run_cycles = config['mouse']['min_run_cycles']
        
        #scale is "base" for acceleration - do adjustments here
        screen_mag = get_mag(tuple(config['screen_size'].values()))
        print(config['screen_size'].values())
        screen_scale = screen_mag / get_mag((1920,1080)) # default scale to 1920 * 1080 - use diagonal number of pixels as scalar
        usr_scale = (config['mouse']['scale_x'], config['mouse']['scale_y']) #user multipliers

        scrn_scale = 1.0
        
        # dynamic mouse configuration      
        slow_thresh = config['mouse']["dynamic_mouse"]['input']['slow']
        fast_thresh = config['mouse']["dynamic_mouse"]['input']['fast']

        # scale amount for slow and fast movement, mid is linear translation between
        slow_scale = config['mouse']["dynamic_mouse"]['output']['slow']
        fast_scale = config['mouse']["dynamic_mouse"]['output']['fast']

        # number of cycles currently idled (reset to 0 on motion)
        idle_count = 0
        dwell_count = 0
        idle_cycles = config['mouse']['idle_duration']
        dwell_cycles = config['mouse']['dwell_duration']
        dwell_repeat = config['mouse']['dwell_repeat']

        # number of cycles run in total
        cycle_count = 0
        dx = 0
        dy = 0
        batcher = (0,0)

        while True:
            # print(".")
            if not Events.move_mouse.is_set():
                cycle_count = 0
                idle_count = 0
                dwell_count = 0
                Events.mouse_idle.clear()
                Events.mouse_dwell.clear()
                batcher = (0,0)
                # DBS.println("move mouse -- awaiting")
                pass
    
            await Events.move_mouse.wait() # only execute when move_mouse is set
            await Events.gesture_not_collecting.wait()
            await Cato.imu.wait()
            if cycle_count == 0:
                DBS.println(f"+ Mouse Live (mem: {gc.mem_free()})")

            cycle_count += 1    # count cycles

            # isolate x and y axes so they can be changed later with different orientations
            x_mvmt = self.imu.gy
            y_mvmt = self.imu.gz
            
            # calculate magnitude and angle for linear scaling
            mag = sqrt(x_mvmt**2 + y_mvmt**2)
            ang = atan2(y_mvmt, x_mvmt)
            
            # pure linear mouse, move number of pixels equal to number of degrees rotation
            if(mouse_type == "LINEAR"):
                pass

            # mouse with dynamic acceleration for fine and coarse control
            if(mouse_type == "ACCEL"):
                scrn_scale = translate(slow_thresh, fast_thresh, slow_scale, fast_scale, mag)
                scrn_scale *= screen_scale

            if( mag <= idle_thresh ): # if too slow
                # if (idle_count == 0): # count time of idle to finish (design util)
                    # print("\tidle detected, count begun")
                idle_count += 1
                dwell_count += 1
            else:
                # print("\tactivity resumed: idle counter reset")
                idle_count = 0
                Events.mouse_idle.clear()
                dwell_count = 0
                Events.mouse_dwell.clear()
            
            if(not Events.mouse_dwell.is_set())and(dwell_count >= dwell_cycles): # if sufficiently idle, set mouse_idle
                DBS.println(f"\t: Mouse_Dwell Set (mem: {gc.mem_free()})")
                if(dwell_repeat):
                    dwell_count = 0
                Events.mouse_dwell.set()
                await asyncio.sleep(0)
            
            if(not Events.mouse_idle.is_set())and(cycle_count >= min_run_cycles)and(idle_count >= idle_cycles): # if sufficiently idle, set mouse_idle
                DBS.println(f"\t: Mouse_Idle Set (mem: {gc.mem_free()})")
                Events.mouse_idle.set()
                await asyncio.sleep(0)

            scale = scrn_scale*mag
            scale = (usr_scale[0]*scale,usr_scale[0]*scale)
            # trig scaling of mouse x and y values
            dx = scale[0] * cos(ang) + batcher[0]
            dy = scale[1] * sin(ang) + batcher[1]
            # c = int(cycle_count/3)
            # dx = 10*(2-(c)%4)*(c%2)       # fast squares
            # dy = 10*(2-(c+1)%4)*((c+1)%2)
            if(abs(dx) < 0.2)and(abs(dy) < 0.2):
                Events.battery.set()
            else:
                Events.battery.clear()

            batcher = (dx-int(dx), dy-int(dy))
            dx, dy = int(dx), int(dy)

            try:
                self.blue.mouse.move(dx, dy, 0)
                if(cycle_count%10 == 0):
                    #print(self.blue.mouse.report)
                    pass
            except ConnectionError as ce:
                DBS.println("ConnectionError: connection lost in move_mouse()")
                DBS.println(str(ce))
            except Exception as ex:
                print(f"OtherException:{ex}")
            
    async def _scroll(self, hall_pass: asyncio.Event = None):
        DBS.println("+ _scroll")
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        hall_pass.set()
        DBS.println("- _scroll")

    async def scroll(self, hall_pass: asyncio.Event = None):
        ''' scrolls the mouse until sufficient exit condition is reached '''
        
        z = 0.0 #value to integrate to manage scroll
        dt = 1.0 / 104.0
        scale = 1.0 # slow down kids

        num_cycles = 0
        while True:
            await Events.scroll.wait() # block if not set
            if num_cycles == 0:
                DBS.println("+ Scroll Running")
            num_cycles += 1

            slow_down = 5 # only scroll one line every N cycles
            for i in range(slow_down):
                await Cato.imu.wait()
            
            z += (-1) * Cato.imu.gz
            no_scroll_thresh = 45.0

            try:
                if z > no_scroll_thresh:
                    self.blue.mouse.move(0, 0, 1)
                elif z <= -1 * no_scroll_thresh:
                    self.blue.mouse.move(0, 0, -1)
            except ConnectionError as ce:
                DBS.println("ConnectionError: connection lost in scroll()")
                DBS.println(str(ce))

            if( abs(Cato.imu.gy) > 30.0 ):
                DBS.println("\t- Scroll Broken")
                num_cycles = 0

                z = 0.0
                Events.scroll_done.set()
                Events.scroll.clear()
                if hall_pass is not None:
                    print("\tSCROLL: Scroll_done set & hall_pass set")
                    hall_pass.set()
    
    async def _scroll_lr(self, hall_pass: asyncio.Event = None):
        # Left/Right Scroll Manager
        # Holds Shift, Sets Scroll, Releases Shift.
        lshift_keycode = 225
        print(f"+ _scroll_lr")
        self.blue.k.press(lshift_keycode)
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        self.blue.k.release(lshift_keycode)
        print(f"b: {gc.mem_free()}")
        if hall_pass is not None:
            DBS.println("\t- _scroll_lr")
            hall_pass.set()
    
    async def event_release(self,actor,*buttons, triggers = None):
        for t in triggers:
            if(t != None):
                await t.wait()
        actor.release(*buttons)
        print(f"EventRelease: {type(actor)} released {buttons}")
    
    '''
        INPUTS
            action(str): string key corresponding to desired action to be performed
            actorInd(int): index of hid object in actor_key to perform specified action on buttons
            *buttons(hex): hex keycodes of buttons to be acted upon
            hall_pass(Event): event indicating completion of method
        OUTPUTS
            None
        DESCRIPTION
            Uses available hid object in actor_key (indexed by actorInd input) to perforrm a common button
            action (from selection of tap, double tap, press, release, and toggle) on specified keycodes
    '''
    async def button_action(self, actorInd:int, action: str, *buttons: hex, hall_pass: asyncio.Event = None):
        actor_key = (self.blue.mouse, self.blue.k)
        if(actorInd not in range(len(actor_key))):
            DBS.println("No hid device with actor index "+str(actorInd))
            hall_pass.set()
            return

        def ispressed(actor,button):
            if(isinstance(actor,type(self.blue.mouse))):
                return not(bool(button & ~(actor.report[0])))
            
            elif(isinstance(actor,type(self.blue.k))):
                modifier = Keycode.modifier_bit(button)
                if(modifier):
                    return not(bool(modifier & ~(actor.report[0])))
                else:
                    ip = False
                    for b in actor.report[2:8]:
                        ip |= (b == button)
                    return ip
            else:
                return False
        

        actor = actor_key[actorInd]
        actor_key = None
        
        if(action == "tap"):
            actor.press(*buttons)
            actor.release(*buttons)

        elif(action == "double_tap"):
            actor.press(*buttons)
            actor.release(*buttons)
            actor.press(*buttons)
            actor.release(*buttons)

        elif(action == "press"):
            actor.press(*buttons)

        elif(action == "release"):
            actor.release(*buttons)

        elif(action == "toggle"):
            for b in buttons:
                if(ispressed(actor,b)):
                    actor.release(b)
                else:
                    actor.press(b)

        elif(action == "hold_until_idle"):
            actor.press(*buttons)
            asyncio.create_task(self.event_release(actor, *buttons, triggers = (Events.gesturing,)))
        elif(action == "hold_until_sig_motion"):
            actor.press(*buttons)
            asyncio.create_task(self.event_release(actor, *buttons, triggers = (Events.gesturing,Events.sig_motion)))
        elif(action == "turbo"):
            thresh = buttons[0]
            buttons = buttons[1:]
            asyncio.create_task(self.wait_for_motion(thresh))
            
            delay = config["gesture"]["turbo_rate"]["initial"]
            minDelay = config["gesture"]["turbo_rate"]["minimum"]
            decay = config["gesture"]["turbo_rate"]["decay_rate"]
            while(not Events.sig_motion.is_set()):
                actor.press(*buttons)
                actor.release(*buttons)
                await asyncio.sleep(delay)
                if(delay > minDelay):
                    delay *= decay
            Events.sig_motion.clear()
        
        else:
            # curretnly undefined behavior for undefined actions
            DBS.println("Custom action:\t"+str(actor)+"."+action+str(*buttons))
            eval("actor."+action+"(*buttons)")
            # this seems terribly unsafe, but could be useful for hacking together macro actions later
        
        hall_pass.set()
        return

    async def all_release(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        try:
            self.blue.mouse.release_all()
            self.blue.k.release_all()
        except ConnectionError as ce:
            DBS.println("ConnectionError: connection lost in all_release()")
            DBS.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()


    async def pin_action(self, pin, action, direction = digitalio.Direction.OUTPUT, hall_pass: asyncio.Event = None):
        digital_pins = ('D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8', 'D9', 'D10')
        # analog_pins = ('A0', 'A1', 'A2', 'A3', 'A4', 'A5')

        # validate pin
        if pin not in digital_pins:
            raise ValueError(f"Invalid Pin. Valid options: {digital_pins}")
        
        # configure pin settings
        if pin not in pins.keys():
            pins.update( {pin : digitalio.DigitalInOut( eval(f"board.{pin}") ) } )
            pins[pin].direction = digitalio.Direction.OUTPUT
        
        # validate action input
        valid_actions = ("set_high", "set_low")
        if action not in valid_actions:
            raise ValueError(f"Invalid Action. Valid options: {valid_actions}")
        
        # execute action 
        # Should this generate a task of its own for something like "blink"?
        # Do I need to hold a handle to preseve its value?
        if action == "set_high":
            pins[pin].value = True
        
        if action == "set_low":
            pins[pin].value = False

        if hall_pass is not None:
            hall_pass.set()


    async def collect_gestures_app():
        Events.gesture_not_collecting.clear()
        # print("Collecting Gesture (wired connection)")
        
        try:
            numRec = 1
            stillTime = 2
            situateTime = 0
            unplugTime = 0
            logPref = "log_"
            with open("gesture.cato",'r') as g:
                lines = g.readlines()
                timeStamp = lines[0].strip()
                gestName = lines[1].strip()
                numRec = int(lines[2])
                logPref = timeStamp+"_"+gestName+"_"
                print(logPref)
                try:
                    stillTime = int(lines[3])
                    situateTime = int(lines[4])
                    unplugTime = int(lines[5])
                except IndexError as ie:
                    print("Not Enough Args")
                    pass
                del(lines)

            import os
            os.remove("gesture.cato")
            print("Removed gesture.cato")
            del(os)

            if(unplugTime > 0):
                timeout = asyncio.create_task(stopwatch(unplugTime))
                import supervisor
                while(supervisor.runtime.usb_connected):
                    await asyncio.sleep(0.5)
                    # print(timeout.done())
                    if(timeout.done()):
                        print("Failed to unplug")
                        print("Reseting")
                        mc.reset()
                timeout.cancel()
                del(timeout)
                print("Unplugged")
                del(supervisor)
            await asyncio.sleep(situateTime)

            print("\nGathering gesture params")
            from utils import config
            gestLen     = config["gesture"]["length"]
            idleLen     = config["gesture"]["idle_cutoff"]
            gestThresh  = config["gesture"]["start_threshold"]
            idleThresh  = config["gesture"]["idle_threshold"]
            # timeout     = config["gesture"]["gc_timeout"]
            print("Removing config and garbage collecting for space")
            del(config)
            gc.collect()
            print("\tmem free:\t",gc.mem_free())
            
            #from utils import pins
            def gyro_mag():
                return get_mag((Cato.imu.gx,Cato.imu.gy,Cato.imu.gz))
            for i in range(1,numRec+1):

                gesture = [(0,0,0,0,0,0,0)]
                mag = 0
                
                pins["led_red"].value = False
                await asyncio.sleep(stillTime)

                pins["led_green"].value = False
                print("\nThrash Window (stalling to let prematurre motion pass)")
                # let premature motion pass
                idle = 0
                count = 0
                while(idle < idleLen):
                    await Cato.imu.wait()
                    mag = gyro_mag()
                    if(mag**2 < gestThresh):
                        idle += 1
                    else:
                        idle = 0
                    count += 1
                    if(count % 6 == 0):
                        print("flash")
                        pins["led_red"].value = not(pins["led_red"].value)
                        pins["led_green"].value = not(pins["led_green"].value)
                pins["led_red"].value = True
                pins["led_green"].value = False

                with open("flag.txt",'w') as flg:
                    flg.write("")
                    pass
                print("\nReady for Gesture Input")
                gc.collect()
                while(mag**2 < gestThresh):
                    await Cato.imu.wait()
                    gesture[0] = (Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz)
                    mag = gyro_mag()

                # actual gesture is performed and recorded here
                print("Recording")
                print("\tmem free:\t",gc.mem_free())
                idle = 0
                while(len(gesture) < gestLen)and(idle < idleLen):
                    await Cato.imu.wait()
                    gesture.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz))
                    mag = gyro_mag()

                    if(mag**2 < idleThresh):
                        idle += 1
                    else:
                        idle = 0

                print("\nGesture Recording Completed")
                pins["led_green"].value = True

                # print("num samples recorded: ",len(gesture))
                gc.collect()
                print("\tmem free:\t",gc.mem_free())
                logName = logPref+str(i)+".txt"
                print(logName)
                with open(logName,'w') as log:
                    l = len(gesture)
                    while(gesture):
                        log.write(",".join(str(v) for v in gesture.pop(0)))
                        log.write("\n")
                        await asyncio.sleep(0)
                    for z in range(l,gestLen):
                        log.write("0,0,0,0,0,0\n")
                import os
                os.remove("flag.txt")
                del(os)
            
            Events.gesture_collecting.clear()
            Events.gesture_not_collecting.set()
            
            print("\nGesture Finnished Logging")
            print("\tmem free:\t",gc.mem_free())
        except Exception as ex:
            print("ERRORED OUT!!")
            try:
                import os
                os.remove("gesture.cato")
            except:
                pass
            print(ex)
        # await asyncio.sleep(5)
        mc.reset()

    async def test_loop(self):
        DBS.println("+ test_loop")
        await asyncio.sleep(2)
        while(True):
            print()
            DBS.println('\t', int(Cato.imu.gx*10), '\t', int(Cato.imu.gy*10), '\t', int(Cato.imu.gz*10))
            await asyncio.sleep(0.2)
    
    
    async def gesture_practice_loop(self):
        DBS.println("+ gesture_loop")
        gestKey = config["gesture"]["key"]
        self.bindings = [0]*(len(gestKey)+1)
        while True:
            prevInterp = list(neuton_outputs)
            await self.gesture_interpreter(indicator = None, timeout = 0)
            if(prevInterp == list(neuton_outputs)):
                continue

            gests = []
            for idx, gesture in enumerate(gestKey[1:]):
                if(neuton_outputs[idx]*100 >= config["practice"]["cutoff"]):
                    gests.append((gesture,neuton_outputs[idx]))
            
            nDisp = min(len(gests),config["practice"]["num_infers"])
            for i in range(nDisp):
                sorted = True
                for j in range(len(gests)-1,i,-1):
                    if(gests[j][1] > gests[j-1][1]):
                        sorted = False
                        temp = gests[j]
                        gests[j] = gests[j-1]
                        gests[j-1] = temp
                if(sorted):
                    break
            for i in range(nDisp, len(gests)):
                gests.pop(i)
            
            outputStr = ""
            if(config["practice"]["dense"]):
                if(not gests):
                    outputStr = "None"
                else:
                    for g in gests:
                        outputStr += g[0]+" "+str(int((g[1]+0.005)*100))+",  "
                    outputStr = outputStr[:-3]
            else:
                if(max(neuton_outputs) >= config["gesture"]["confidence_threshold"]):
                    outputStr = gestKey[self.n.inference()+1]
                else:
                    outputStr = "None"

                outputStr += "\n"
                for idx, gesture in enumerate(gestKey[1:]):
                    outputStr += f"\t{gesture:12}\t{int((neuton_outputs[idx]+0.005)*100):>3n}\n"
            
            DBS.println("typing:\n"+outputStr)
            await self.blue_type(outputStr+'\n')
            # await asyncio.sleep(1)
    
    async def blue_type(self, str):
        ##maybe a more robust version of this exists somewhere; worth looking into?
        for c in str:
            if(ord(c) >= 97):
                c = ord(c) - 93
            elif(ord(c) >= 65):
                self.blue.k.press(225)  #LShift
                await asyncio.sleep(0.01)
                c = ord(c) - 61
            elif(ord(c) < 48):
                if(c == ' '):
                    c = 44
                elif(c == '\t'):
                    c = 43
                elif(c == '\n'):
                    c = 40  #Enter
                elif(c == '.'):
                    c = 55
                elif(c == ','):
                    c = 54
            elif(c == '0'):
                c = 39
            else:
                c = int(c) + 29
            self.blue.k.press(c)
            #await asyncio.sleep(0.005)
            self.blue.k.release_all()
        #await asyncio.sleep(0.05)
    