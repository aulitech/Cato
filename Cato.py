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

from adafruit_hid.keycode import Keycode

from math import sqrt, atan2, sin, cos
import array

from battery import Battery
from imu import LSM6DS3TRC

import asyncio

import gc

from neutonml import Neuton

from StrUUIDService import config
from StrUUIDService import DebugStream as DBS

#helpers and enums

class EV(): #these are actually gestures
    gesture_key = [ # TODO: Pull the names from config
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
    sleep                   = asyncio.Event()   # indicates time to go to sleep
    wait_for_motion         = asyncio.Event()   # wait_for_motion
    wait_for_motion_done    = asyncio.Event()   # wait-for-motion exit indicator
    feed_neuton             = asyncio.Event()   # prevent multiple instances of neuton being fed
    sig_motion              = asyncio.Event()   # indicates that there has been significant motion during wait_for_motion's window
    stream_imu              = asyncio.Event()   # stream data from the imu onto console -- useful for debugging
    mouse_event             = asyncio.Event()   # triggers detection of Cato gesture
    idle                    = asyncio.Event()   # triggered when no events change for some time

    gesture_collecting      = asyncio.Event()   # signal that collect_gestures() is currently running
    gesture_not_collecting  = asyncio.Event()
    gesture_not_collecting.set()

# Home for neuton inference
neuton_outputs = array.array( "f", [0]*len(EV.gesture_key) )

def mem( loc = "" ):
    print(f"Free Memory at {loc}: \n\t{gc.mem_free()}")

from WakeDog import WakeDog

class Cato:
    ''' Main Class of Cato Gesture Mouse '''

    imu = LSM6DS3TRC()

    def __init__(self, bt:bool = True, do_calib = True):
        '''
            ~ @param bt: True configures and connect to BLE, False provides dummy connection
            ~ @param do_calib: True runs calibration, False disables for fast/lazy startup
        '''
        DBS.println("+ Cato Init")


        #specification for operation
        self.specs = {
            "freq" : 104.0, # imu measurement frequency (hz)
            "g_dur": 0.75   # gesture duration (s)
        }

        self.hall_pass = asyncio.Event() # separate event to be passed to functions when we must ensure they finish

        # battery managing container
        self.battery = Battery()

        if bt:
            import BluetoothControl
        else:
            import DummyBT as BluetoothControl
        
        self.blue = BluetoothControl.BluetoothControl()

        self.state = 0

        mode = config["operation_mode"]
        if(mode < len(config["bindings"])):
            self.bindings = config["bindings"][mode]

        # Mode-dependent task spawning
        """ MODE CODE MEANINGS
                0 - 9: USER MODES
                    0:  Default Computer
                    1:  Default Television
                    2:  Forever Pointer (only pointer)
                    3:  Forever Clicker (only clicker - tap detect)
                10-19: Dev Test Modes:
                    10: Test Loop -- bluetooth print test
                x>=20: unused
        """
        if(mc.nvm[2]):
            mc.nvm[2] = False
            self.tasks = {
                "collect_gesture"   : asyncio.create_task(Cato.collect_gestures_wired())    
            }
        elif(mode == 0):
            self.tasks = {
                "wait_for_motion"   : asyncio.create_task(self.wait_for_motion()),
                "move_mouse"        : asyncio.create_task(self.move_mouse()),
                "mouse_event"       : asyncio.create_task(self.mouse_event()),
                "scroll"            : asyncio.create_task(self.scroll()),
                "sleep"             : asyncio.create_task(self.go_to_sleep()),
                #"collect_gestures"  : asyncio.create_task(Cato.collect_gestures_app())
            }
        elif(mode == 1):
            self.tasks = {
                "wait_for_motion"   : asyncio.create_task(self.wait_for_motion()),
                "tv_control"        : asyncio.create_task(self.tv_control()),
                #"sleep"             : asyncio.create_task(self.go_to_sleep()),
                #"collect_gestures"  : asyncio.create_task(Cato.collect_gestures_app())
            }
        
        elif(mode == 2):
            self.tasks = {
                "point" : asyncio.create_task(self.move_mouse(forever = True)),
                "sleep" : asyncio.create_task(self.go_to_sleep())
            }
        elif(mode == 3):
            self.tasks = {
                "clicker"           : asyncio.create_task(self.clicker_task()),
                #"collect_gestures"  : asyncio.create_task(Cato.collect_gestures_app()),
                "sleep"             : asyncio.create_task(self.go_to_sleep()),
            }
        elif(mode >= 10):
            self.tasks = {
                "test_loop"         : asyncio.create_task(self.test_loop())

            }
            '''
            if(mode == 10):
                self.tasks["collect_gestures"] = asyncio.create_task(Cato.collect_gestures_app())
            elif(mode == 11):
                self.tasks["wait_for_motion"] = asyncio.create_task(Cato.wait_for_motion())
            '''
        
        self.tasks.update( {"monitor_battery"   : asyncio.create_task(self.monitor_battery())} )
        self.tasks.update(Cato.imu.tasks)   # functions for t1he imu
        self.tasks.update(self.blue.tasks)  # functions for bluetooth
        self.tasks.update(WakeDog.tasks)    # functions for waking / sleeping monitoring

        self.n = Neuton(outputs=neuton_outputs)
        self.gesture = EV.NONE

        self.led_pin = board.LED_GREEN
        self.led = digitalio.DigitalInOut(self.led_pin)
        self.led.direction = digitalio.Direction.OUTPUT

        DBS.println("- Cato Init")
    
    async def reboot():
        mc.reset()

    
    async def go_to_sleep(self):
        # This method sets a Cato to go to sleep - presently after exactly 15 seconds, soon to be based on inactivity
        while True:
            # await asyncio.sleep(1) # TAKE IMU READINGS BEFORE TRYING TO GO BACK TO SLEEP?
            await Events.sleep.wait()
            self.tasks['interrupt'].cancel() #release pin int1
            await asyncio.sleep(0.1)

            self.imu.single_tap_cfg() # set wakeup condn to single tap detection

            pin_alarm = alarm.pin.PinAlarm(pin = board.IMU_INT1, value = True) #Create pin alarm
            
            # ensure that LED is OFF
            while( self.led.value == False ):
                await asyncio.sleep(0.001)

            print("LIGHT SLEEP")
            alarm.light_sleep_until_alarms(pin_alarm)
            print("WOKE UP")
            Events.sleep.clear()
            del(pin_alarm) # release imu_int1

            Cato.imu.data_ready_on_int1_setup() #setup imu data ready

            self.tasks['interrupt'] = asyncio.create_task( Cato.imu.interrupt() )
            WakeDog.feed()
            #await asyncio.sleep(1) # TAKE IMU READINGS BEFORE TRYING TO GO BACK TO SLEEP?

    async def monitor_battery(self):
        while True:
            for i in range(3):
                await asyncio.sleep(0.2)
                self.led.value = False
                await asyncio.sleep(0.2)
                self.led.value = True
            await asyncio.sleep(5)
            temp = self.battery.raw_value
            # DBS.println(f"bat_ena True: {temp[0]}")
            await asyncio.sleep(0.1)
            # DBS.println(f"bat_ena False: {temp[1]}")
            self.blue.battery_service.level = self.battery.level

    async def _move_mouse(self, hall_pass: asyncio.Event = None):
        Events.move_mouse.set()
        await Events.mouse_done.wait()
        Events.mouse_done.clear()
        hall_pass.set()

    async def center_mouse_cursor(self, hall_pass: asyncio.Event = None):
        x = config["screen_size"][0]
        y = config["screen_size"][1]
        try:
            self.blue.mouse.move(-2 * x, -2 * y)
            self.blue.mouse.move(int(0.5*x), int(0.5*y))
        except ConnectionError as ce:
            DBS.println("ConnectionError: connection lost in center_mouse_cursor()")
            DBS.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()
    
    async def block_on(self, coro, *args):
        '''
            await target function having uncertain runtime which also needs to use async imu functionality  \n
            coro: Coroutine or other awaitable
        '''
        await coro( *args, hall_pass=self.hall_pass)
        await self.hall_pass.wait()
        self.hall_pass.clear()
    
    async def mouse_event(self): 
        ''' calls to gesture detection libraries '''
        while True:
            await Events.mouse_event.wait()
            Events.mouse_event.clear()
            await Events.gesture_not_collecting.wait()
            target = await self.gesture_interpreter()
            #print(f"\tGot \"{target_name}\" at mouse_event")
            #DBS.println(f"Detect Event -- Dispatching: self.{target_name}")
            await self.block_on(eval("self."+target[0], {"self":self}),*target[1:])
            print(f"\t \"{target}\" finished at mouse_event")
            
            #DBS.println("Detect Event: Finished Dispatching")
            Events.control_loop.set()
    
    #TODO: refactor to use button_action exclusively
    async def tv_control(self):
        Cato.imu.data_ready_on_int1_setup()
        turbo_terminate = asyncio.Event()
        task_dict = {
            "noop"  :   None,
            "up"    :   (self.turbo_input,
                            (self.type_up_key, config["turbo_rate"], turbo_terminate)),
            "down"  :   (self.turbo_input,
                            (self.type_down_key, config["turbo_rate"], turbo_terminate)),
            "left"  :   (self.turbo_input,
                            (self.type_left_key, config["turbo_rate"], turbo_terminate)),
            "right" :   (self.turbo_input,
                            (self.type_right_key, config["turbo_rate"], turbo_terminate)),
            "enter" :   (self.type_enter_key,()),
            "esc"   :   (self.type_esc_key,()),
            "meta"  :   (self.type_meta_key,())
        }
        task = None
        prev_task = "noop"
        DBS.println("tv_control")
        while True:
            await Events.gesture_not_collecting.wait()
            task_name = await self.tv_interpreter()

            # needs a check for sigMotion upon new gestInterpreter
            # needs a check for sigMotion upon new gestInterpreter
            if(Events.sig_motion.is_set())and(task != None):
                turbo_terminate.set()
                await task
                turbo_terminate.clear()

            if(task_name != "noop"):                
                func_tuple = task_dict[task_name]
                if((func_tuple[0].__name__ != self.turbo_input.__name__) or (task_name != prev_task)):
                    task = asyncio.create_task(func_tuple[0](*func_tuple[1]))
                    prev_task = task_name
                else:
                    prev_task = "noop"
                await asyncio.sleep(0.3)
            elif(Events.sig_motion.is_set()):
                prev_task = "noop"

    async def gesture_interpreter(self):
        DBS.println("+gesture_interpreter mem: ",gc.mem_free())
        infer = EV.NONE
        confThresh = config["confidence_threshold"]

        param = config["gesture"]
        maxLen = param["length"]
        idleLen = param["idle_cutoff"]
        gestThresh = param["movement_threshold"]
        idleThresh = param["idle_threshold"]
        timeout = param["timeout"]
        param = None

        length = 1
        mag = 0

        idle = 0
        while(idle < idleLen):
            await Cato.imu.wait()
            mag = (Cato.imu.gx)**2 + (Cato.imu.gy)**2 + (Cato.imu.gz)**2
            if(mag < gestThresh):
                idle += 1
            else:
                DBS.println("Premature Motion")
                return ["noop"]
        
        shakeCursor = asyncio.create_task(self.shake_cursor()) #ADD PRINT TO SHAKE CURSOR
        DBS.println("+ MouseEvent: Looking for Gesture")
        Events.sig_motion.clear()

        # wait to recieve significant motion and return if the timeout threshold is passed
        timeoutEv = asyncio.Event()
        asyncio.create_task(Cato.stopwatch(timeout, ev = timeoutEv))
        while(mag < gestThresh):
            if(timeoutEv.is_set()):
                DBS.println("No Gesture Caused Timout")
                return self.bindings[EV.NONE][self.state]
            await Cato.imu.wait()
            mag = (Cato.imu.gx)**2 + (Cato.imu.gy)**2 + (Cato.imu.gz)**2
            #DBS.println((Cato.imu.gx,Cato.imu.gy,Cato.imu.gz,mag))

        # motion recieved
        DBS.println("Motion Recieved: ",(Cato.imu.gx,Cato.imu.gy,Cato.imu.gz,mag))
        Events.sig_motion.set()
        self.n.set_inputs(
            array.array('f', [Cato.imu.ax, Cato.imu.ay, Cato.imu.az, 
                              Cato.imu.gx, Cato.imu.gy, Cato.imu.gz]))

        # feed neuton until idled for 'idleLen' loops
        idle = 0
        while(length < maxLen)and(idle < idleLen):
            await Cato.imu.wait()
            data = array.array('f',[Cato.imu.ax, Cato.imu.ay, Cato.imu.az,
                                    Cato.imu.gx, Cato.imu.gy, Cato.imu.gz])
            if(not self.n.set_inputs(data)):
                break
            mag = (Cato.imu.gx)**2 + (Cato.imu.gy)**2 + (Cato.imu.gz)**2
            #DBS.println((Cato.imu.gx,Cato.imu.gy,Cato.imu.gz,mag))
            length += 1

            if(mag < idleThresh):
                idle += 1
            else:
                idle = 0
        DBS.println("Gesture Length: ",length)
        if(idle == idleLen):
            DBS.println("Broke for idle timeout")
        elif(length == maxLen):
            DBS.println("Broke for full gesture")
        else:
            DBS.println("Broke for premature neuton fill")

        # fill remaining space w 0's
        while(idle == idleLen)and(length < maxLen):
            length += 1
            if(not self.n.set_inputs(array.array('f', [0]*6)))and(length < maxLen):
                DBS.println("WARNING: PREMATURE NEUTON FILL")
                break
        DBS.println("Filled length: ", length)

        infer = self.n.inference()+1
        DBS.println(neuton_outputs)
        if(max(neuton_outputs) < confThresh):
            infer = 0

        await shakeCursor
        DBS.println("-gesture_interpreter mem: ",gc.mem_free())
        return self.bindings[infer][self.state]
    
    async def feed_neuton(self, log):
        await Events.feed_neuton.wait()
        Events.feed_neuton.clear()
        DBS.println("Feeding Neuton")
        for data in log:
            if(not self.n.set_inputs(data)):
                break
        DBS.println("Successful Feed")
    
    # TODO: unimplement this method after tv refactor
    async def turbo_input(self, coro, rate, terminator: asyncio.Event):
        delay = rate[0]
        while(not(terminator.is_set())):
            DBS.print(delay,":\n\t")
            await coro()
            await asyncio.sleep(delay)
            if(delay > rate[1]):
                delay *= rate[2]
    
    # Cato Actions
    # CircuitPython Docs: https://docs.circuitpython.org/projects/hid/en/latest/api.html#adafruit-hid-mouse-mouse '''
    async def noop(self, hall_pass: asyncio.Event = None):
        ''' no operation '''
        # DBS.println("nooping")
        if hall_pass is not None:
            hall_pass.set()

        
    # Cato Mouse Actions
    async def shake_cursor(self, hall_pass: asyncio.Event = None):
        mv_size = 4
        num_wiggles = 1
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

        try:
            for wiggle in range(num_wiggles):
                for move in moves:
                    for _ in range(2):
                        await asyncio.sleep(0.02)
                        self.blue.mouse.move( *move )
        except ConnectionError as ce:
            DBS.println("ConnectionError: connection lost in shake_cursor()")
            DBS.println(str(ce))
        
        if hall_pass is not None:
            hall_pass.set()

    def translate(x_min, x_max, y_min, y_max, input):
        if input < x_min:
            return y_min
        if input > x_max:
            return y_max
        
        x_span = x_max - x_min
        y_span = y_max - y_min
        
        scaled = (y_span / x_span) * (input - x_min)
        shifted = scaled + y_min
        return shifted

    async def clicker_task(self):
        Cato.imu.single_tap_cfg()
        while True:
            await Cato.imu.wait()
            try:
                #DBS.println("Click")
                self.blue.mouse.click(self.blue.mouse.LEFT_BUTTON)
            except ConnectionError as ce:
                DBS.println("ConnectionError: connection lost in clicker_task()")
                DBS.println(str(ce))

    async def quick_calibrate(self, hall_pass: asyncio.Event = None):
        await asyncio.sleep(0.5)
        await asyncio.create_task(Cato.imu.calibrate(100))
        await asyncio.create_task(self.shake_cursor())
        hall_pass.set()

    async def quick_sleep(self, hall_pass: asyncio.Event = None):
        Events.sleep.set()
        hall_pass.set()


    async def move_mouse(self, max_idle_cycles=80, mouse_type = "LINEAR", forever: bool = False):
        '''
            move the mouse via bluetooth until sufficiently idle
        '''
        # mem("move_mouse -- pre settings load")
        
        cfg = config['mouse']

        idle_thresh = cfg['idle_thresh'] # speed below which is considered idle  
        min_run_cycles = cfg['min_run_cycles']
        
        #scale is "base" for acceleration - do adjustments here
        screen_size = config['screen_size']
        screen_mag = sqrt(screen_size[0] ** 2 + screen_size[1] ** 2)
        screen_scale = screen_mag / sqrt(1920**2 + 1080**2) # default scale to 1920 * 1080 - use diagonal number of pixels as scalar
        scale = 1.0
        usr_scale = cfg['scale'] #user multiplier

        # dps limits for slow vs mid vs fast movement        
        slow_thresh = cfg['slow_thresh']
        fast_thresh = cfg['fast_thresh']

        # scale amount for slow and fast movement, mid is linear translation between
        slow_scale = cfg['slow_scale']
        fast_scale = cfg['fast_scale']

        # number of cycles currently idled (reset to 0 on motion)
        idle_count = 0

        # number of cycles run in total
        cycle_count = 0
        dx = 0
        dy = 0
        dscroll = 0

        # mem("post_cfg") # At this point, between pre and post, we lost only 100bytes

        while True:
            # print(".")
            if not Events.move_mouse.is_set():

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
                scale = Cato.translate(slow_thresh, fast_thresh, slow_scale, fast_scale, mag)
                scale *= screen_scale

            # Begin idle checking -- only after minimum duration
            if(cycle_count >= min_run_cycles and not forever):
                if( mag <= idle_thresh ): # if too slow
                    # if (idle_count == 0): # count time of idle to finish (design util)
                        # print("\tidle detected, count begun")
                    idle_count += 1
                else:
                    # print("\tactivity resumed: idle counter reset")
                    idle_count = 0

                if idle_count >= max_idle_cycles: # if sufficiently idle, clear move_mouse
                    DBS.println(f"\t- Mouse Exit (mem: {gc.mem_free()})")

                    Events.move_mouse.clear()
                    Events.mouse_done.set()

                    idle_count = 0
                    cycle_count = 0

            mag = mag * usr_scale
            # trig scaling of mouse x and y values
            dx = int( scale * mag * cos(ang) )
            dy = int( scale * mag * sin(ang) )

            try:
                self.blue.mouse.move(dx, dy, dscroll)
            except ConnectionError as ce:
                DBS.println("ConnectionError: connection lost in move_mouse()")
                DBS.println(str(ce))
            
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
        dt = 1.0 / self.specs["freq"]
        scale = 1.0 # slow down kids

        num_cycles = 0
        while True:
            await Events.scroll.wait() # block if not set
            if num_cycles == 0:
                DBS.println("+ Scroll Running")
            num_cycles += 1

            slow_down = 10 # only scroll one line every N cycles
            for i in range(slow_down):
                await Cato.imu.wait()
            
            z += (-1) * scale * Cato.imu.gz * dt

            try:
                self.blue.mouse.move(0, 0, int(z))
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
        print(f"+ _scroll_lr")
        self.blue.k.press(Keycode.LEFT_SHIFT)
        Events.scroll.set()
        await Events.scroll_done.wait()
        Events.scroll_done.clear()
        self.blue.k.release(Keycode.LEFT_SHIFT)
        print(f"b: {gc.mem_free()}")
        if hall_pass is not None:
            DBS.println("\t- _scroll_lr")
            hall_pass.set()
    
    '''
    INPUTS
        action(str): string key corresponding to desired action to be performed
        actor(int): index of hid object in actor_key to perform specified action on buttons
        *buttons(hex): hex keycodes of buttons to be accted upon
        hall_pass(Event): event indicating completion of method
    OUTPUTS
        None
    DESCRIPTION
        Uses available hid object in actor_key (indexed by actor input) to perforrm a common button
        action (from selection of tap, double tap, press, release, and toggle) on specified keycodes'''
    async def button_action(self, actor:int, action: str, *buttons: hex, hall_pass: asyncio.Event = None):
        actor_key = (self.blue.mouse, self.blue.k)
        if(actor in range(len(actor_key))):
            actor = actor_key[actor]
        else:
            DBS.println("No hid device with actor index "+str(actor))
            hall_pass.set()
            return
        actor_key = None

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

        elif(action == "turbo"):
            #TODO
            DBS.println("turbo button-action not functional")
        
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
        except ConnectionError as ce:
            DBS.println("ConnectionError: connection lost in all_release()")
            DBS.println(str(ce))
        if hall_pass is not None:
            hall_pass.set()
        
    # cato keyboard actions
    async def type_enter_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.ENTER)
        self.blue.k.release(Keycode.ENTER)
        if hall_pass is not None:
            hall_pass.set()
    
    async def type_esc_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.ESCAPE)
        self.blue.k.release(Keycode.ESCAPE)
        if hall_pass is not None:
            hall_pass.set()

    async def type_meta_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.GUI)
        self.blue.k.release(Keycode.GUI)
        if hall_pass is not None:
            hall_pass.set()
    
    async def type_up_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.UP_ARROW)
        self.blue.k.release(Keycode.UP_ARROW)
        if hall_pass is not None:
            hall_pass.set()
    
    async def type_down_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.DOWN_ARROW)
        self.blue.k.release(Keycode.DOWN_ARROW)
        if hall_pass is not None:
            hall_pass.set()
    
    async def type_left_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.LEFT_ARROW)
        self.blue.k.release(Keycode.LEFT_ARROW)
        if hall_pass is not None:
            hall_pass.set()
    
    async def type_right_key(self, hall_pass: asyncio.Event = None):
        ''' docstring stub '''
        self.blue.k.press(Keycode.RIGHT_ARROW)
        self.blue.k.release(Keycode.RIGHT_ARROW)
        if hall_pass is not None:
            hall_pass.set()

    # ToDo, the rest of the keyboard buttons

    @property
    def o_str(self):
        return "{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f},{:.2f}".format(self.last_read, Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz)

    async def _wait_for_motion(self, hall_pass: asyncio.Event = None):
        Events.wait_for_motion.set()
        await Events.wait_for_motion_done.wait()
        Events.wait_for_motion_done.clear()
        hall_pass.set()

    async def wait_for_motion(self, thresh = 150, *, num = -1):
        #NOTE: THIS COULD BE MADE MUCH CHEAPER WITH THE INT1_SIGN_MOT INTERRUPT!
        """
            thresh      = threshold of motion to break loop             \n
            num         = number of cycles max before return False      \n
                -1          = indefinite wait for motion                \n
                Positive Int= breaks after num loops
        """
        cycles = 0 # count number of waited cycles
        val = 0.0
        while True:
            # print("A: ", gc.mem_free())
            
            await Events.wait_for_motion.wait()
            Events.sig_motion.clear()
            # DBS.println("+ Wait_for_motion triggered")
            # DBS.println("B: ", gc.mem_free())
            await Cato.imu.wait()
            # DBS.println("C: ", gc.mem_free())
            cycles += 1

            val = Cato.imu.gx ** 2 + Cato.imu.gy ** 2 + Cato.imu.gz ** 2

            # BREAK CONDN 1: SIGNIFICANT MOTION
            if val > thresh:
                Events.wait_for_motion.clear()
                Events.sig_motion.set()
            # if cycles > 60*104:
            #     Events.sleep.set()
            #     await asyncio.sleep(0)
                Events.sleep.clear()
            #Break CONDN 2: TIMEOUT
            if num != -1:
                if cycles > num:
                    Events.wait_for_motion.clear()
                    Events.sig_motion.clear()
            # print("D: ", gc.mem_free())
            # exiting cleanup
            if not Events.wait_for_motion.is_set():
                exit_reason = "MOTION" if Events.sig_motion.is_set() else "TIMEOUT"
                # DBS.println( f"WAIT FOR MOTION: EXIT : { exit_reason }" )
                Events.wait_for_motion_done.set()
                cycles = 0
            # DBS.println("E: ", gc.mem_free())
            # DBS.println("")
    '''
    async def collect_gestures_app():
        from StrUUIDService import SUS
        SUS.collGestUUID = "AWAITING INTERACTION"
        Events.gesture_not_collecting.set()
        while(True):
            if(SUS.collGestUUID[:2] == "CG"):
                Events.gesture_collecting.set()
                Events.gesture_not_collecting.clear()
                DBS.println("Collecting Gesture (app)")
                #try:
                gestID : int
                gestLength = config["gesture_length"]
                timeLimit = config["gc_time_window"]

                args = SUS.collGestUUID[2:].split(',')
                if(len(args) > 3):
                    raise Exception("Too many input args (expects 1-3 ints)")
                gestID = int(args[0])
                if(gestID < 0)or(gestID >= len(EV.gesture_key)):
                    raise Exception("Gesture ID "+gestID+" does not exist")
                
                if(len(args) >= 2):
                    gestLength = int(args[1])
                if(len(args) == 3):
                    timeLimit = int(args[2])
                del(args)
                

                hist = []
                maxGest = []
                maxMag = 0
                drift : tuple


                DBS.println("Recording")

                while(len(hist) < gestLength):
                    await Cato.imu.wait()
                    hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))

                drift = hist[gestLength-1]
                maxGest = hist.copy()
                maxMag = maxGest[int(gestLength/2)]
                DBS.println(maxMag)
                for g in maxMag:
                    DBS.println(type(g))
                maxMag = (maxMag[3]-drift[3])**2 + (maxMag[4]-drift[4])**2 + (maxMag[5]-drift[5])**2
                sw = asyncio.create_task(Cato.stopwatch(timeLimit))  # Timer starts here
                DBS.println("Perform Gesture: ", EV.gesture_key[gestID],"(",str(gestID),")")
                SUS.collGestUUID = "Perform Gesture: " + EV.gesture_key[gestID]+"("+str(gestID)+")"
                
                while(not sw.done()):
                    await Cato.imu.wait()
                    hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
                    hist.pop(0)

                    currMid = hist[int(gestLength/2)]
                    currMag = (currMid[3]-drift[3])**2 + (currMid[4]-drift[4])**2 + (currMid[5]-drift[5])**2
                    if(currMag > maxMag):
                        DBS.println("New Max Read")
                        DBS.println(currMag, ">", maxMag)
                        maxMag = currMag
                        maxGest = hist.copy()

                DBS.println("Gesture Recording Completed")

                while(len(maxGest) > 0):
                    d = maxGest.pop(0)
                    SUS.collGestUUID = ','.join(str(v) for v in d)
                    await asyncio.sleep(0)  ##prob dont need sleep but leaving in for safety

                # except Exception as ex:
                #     SUS.collGestUUID = "EX: "+str(ex)
                #     DBS.println(ex)
                
                Events.gesture_collecting.clear()
                Events.gesture_not_collecting.set()
            else:
                await asyncio.sleep(0.1)
    #'''

    async def collect_gestures_wired():
        try:
            #from StrUUIDService import SUS
            #SUS.collGestUUID = "go"
            mc.nvm[2] = 0

            Events.gesture_collecting.set()
            Events.gesture_not_collecting.clear()
            DBS.println("Collecting Gesture (wired)")
            gestID : int
            gestLength = config["gesture_length"]
            timeLimit = config["gc_time_window"]

            '''
            SUS.collGestUUID = "stop"
            while(SUS.collGestUUID == "stop"):
                await asyncio.sleep(0.1)
            '''
            try:
                with open("config.cato",'r') as cgFlag:
                    gestID = int(cgFlag.readline())
            except Exception as ex:
                DBS.println(ex)
                gestID = 10
            if(gestID < 0)or(gestID >= len(EV.gesture_key)):
                import os
                os.remove("config.cato")
                raise Exception("Gesture ID "+gestID+" does not exist")
            
            hist = []
            maxGest = []
            maxMag = 0
            drift : tuple

            DBS.println("Recording")

            while(len(hist) < gestLength):
                await Cato.imu.wait()
                hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
            try:
                import os
                os.remove("config.cato")
            except:
                DBS.println("Failed to delete config.cato")
            '''''
            with open("flag.txt",'w') as flag:
                #from StrUUIDService import SUS
                SUS.collGestUUID = "FLAGGED"
                pass
            #'''
            '''
            SUS.collGestUUID = "stop"
            while(SUS.collGestUUID == "stop"):
                await asyncio.sleep(0.1)
            print("Files Modified")
            '''
            drift = hist[gestLength-1]
            maxGest = hist.copy()
            maxMag = maxGest[int(gestLength/2)]
            DBS.println(maxMag)
            for g in maxMag:
                DBS.println(type(g))
            maxMag = (maxMag[3]-drift[3])**2 + (maxMag[4]-drift[4])**2 + (maxMag[5]-drift[5])**2
            sw = asyncio.create_task(Cato.stopwatch(timeLimit))  # Timer starts here
            DBS.println("Perform Gesture: ", EV.gesture_key[gestID],"(",str(gestID),")")
            
            while(not sw.done()):
                print(mem())
                await Cato.imu.wait()
                hist.append((Cato.imu.ax, Cato.imu.ay, Cato.imu.az, Cato.imu.gx, Cato.imu.gy, Cato.imu.gz, gestID))
                hist.pop(0)

                currMid = hist[int(gestLength/2)]
                currMag = (currMid[3]-drift[3])**2 + (currMid[4]-drift[4])**2 + (currMid[5]-drift[5])**2
                if(currMag > maxMag):
                    DBS.println("New Max Read")
                    DBS.println(currMag, ">", maxMag)
                    maxMag = currMag
                    maxGest = hist.copy()

            DBS.println("Gesture Recording Completed")
            with open("log.txt",'w') as log:
                print(mem())
                while(len(maxGest) > 0):
                    d = maxGest.pop(0)
                    log.write(",".join(str(v) for v in d))
                    log.write("\n")
                    await asyncio.sleep(0)
            
            Events.gesture_collecting.clear()
            Events.gesture_not_collecting.set()
            
            '''
            SUS.collGestUUID = "stop"
            while(SUS.collGestUUID == "stop"):
                await asyncio.sleep(0.1)
            '''
        except Exception as ex:
            import os
            os.remove("config.cato")
            raise(ex)
        mc.reset()
    
    async def stopwatch(n : float,ev : asyncio.Event = None):
        if(n > 0):
            await asyncio.sleep(n)
            if(ev is not None):
                ev.set()

    async def test_loop(self):
        DBS.println("+ test_loop")
        #from StrUUIDService import SUS
        #SUS.collGestUUID = "test_loop"
        #await self.blue.is_connected.wait()
        i = 0
        t = asyncio.create_task(Cato.stopwatch(10))

        while(True):
            DBS.println("looping")
            DBS.print(self.imu.gyro_vals)
            i += 1
            await asyncio.sleep(2)