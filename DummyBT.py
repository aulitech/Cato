class Button:

    def press(self):
        pass
    def release(self):
        pass


class Mouse:
    def __init__(self):
        self.LEFT_BUTTON = 0
        self.RIGHT_BUTTON = 1
        self.MIDDLE_BUTTON = 2
    def move(self, x, y, scroll):
        pass
    def click(self, button):
        pass
    def press(self, button):
        pass
    def release(self, button):
        pass


class Keys:
    def press(self, button):
        pass
    def release(self, button):
        pass
    def release_all(self, button):
        pass

class BluetoothControl:
    def __init__(self):
        self.hid = 0
        self.device_info = 0
        self.advertisement = 0
        self.scan_response = 0
        self.ble = 0

        self.k = Keys()
        self.mouse = Mouse()
        
    def connect_bluetooth(self):
        print("Dummy Connection")
        print("    Connected")
