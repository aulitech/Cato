# Cato docs

    Hello and welcome to CATO, an aulitech alternative communication device for everyone

    This device can be used as
        A bluetooth mouse
        A television remote

## Programming the device

    coming soon

## Using the device

    Cato connects to devices via bluetooth under the name "Cato"

    It must be mounted narrow-end first, on the left side of a pair of glasses (to be opened to other orientations soon)

    When booted or restarted, the device runs a calibration check, in which it must be held still

### Once connected

    The board alternates between two modes:

    Mode 1: Detecting Gestures

    Mode 2: Moving the mouse

#### Mode 1: Detecting Gestures

    Cato detects nods in each of 4 directions (up, down, right, left) 

    It detects rolling (left ear -> left shoulder; right ear -> right shoulder)

    It detects "Yes" and "No"

    Those gestures are mapped as:

    self.st_matrix = [

        #       ST.IDLE                     ST.MOUSE_BUTTONS            ST.KEYBOARD
        
            [   self.move_mouse,            self.to_idle,               self.to_idle        ], #EV.UP           = 0
            
            [   self.left_click,            self.left_click,            self.press_enter    ], #EV.DOWN         = 1
            
            [   self.scroll,                self.noop,                  self.noop           ], #EV.RIGHT        = 2
            
            [   self.hang_until_motion,     self.noop,                  self.noop           ], #EV.LEFT         = 3
            
            [   self.scroll_lr,             self.noop,                  self.noop           ], #EV.ROLL_R       = 4
            
            [   self.scroll_lr,             self.noop,                  self.noop           ], #EV.ROLL_L       = 5
            
            [   self.double_click,          self.noop,                  self.noop           ], #EV.SHAKE_YES    = 6
            
            [   self.hang_until_motion,     self.noop,                  self.noop           ], #EV.SHAKE_NO     = 7
            
            [   self.noop,                  self.noop,                  self.noop           ]  #EV.NONE         = 8
            
    ]