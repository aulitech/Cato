
from imu import LSM6DS3TRC
from BluetoothControl import BluetoothControl as BTC

import asyncio

class MinPointer:
    
    imu = LSM6DS3TRC()
    mouse_ena = asyncio.Event()
    blue = BTC()

    def __init__(self):
        self.tasks = {
            "move_mouse" : asyncio.create_task( self.move_mouse() )
        }
        self.tasks.update(MinPointer.blue.tasks)
        self.tasks.update(MinPointer.imu.tasks)

    async def move_mouse(self):
        #setup zone
        batcher = (0, 0)
        scale = 0.25
        while True:
            await MinPointer.mouse_ena.wait()
            await MinPointer.imu.wait()
            dx = scale * (MinPointer.imu.gy + batcher[0])
            dy = scale * (MinPointer.imu.gz + batcher[1])
            batcher = (dx - int(dx), dy - int(dy))
            dx, dy = int(dx), int(dy)
            MinPointer.blue.mouse.move(dx, dy, 0)
            

