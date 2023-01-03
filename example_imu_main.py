# main.py -- driver code for Cato

from adafruit_lsm6ds import LSM6DS, LSM6DS_DEFAULT_ADDRESS, RWBit, RWBits, const, ROUnaryStruct
import digitalio
import board
import busio 

import supervisor as sp


from imu import LSM6DS3TRC as LSM

import asyncio
import countio

sensor = None 
imupwr = None
imu_i2c = None

async def setup_imu():
    global sensor, imupwr, imu_i2c
    imupwr = digitalio.DigitalInOut(board.IMU_PWR)
    imupwr.direction = digitalio.Direction.OUTPUT
    imupwr.value = True
    await asyncio.sleep(0.1)
    
    imu_i2c = busio.I2C(board.IMU_SCL, board.IMU_SDA)

    sensor = LSM(imu_i2c)
    sensor.int1_ctrl = 0x02
    # sensor.master_cfg = 0x40

    return True

async def imu_interrupt(event):
    event.set()
    with countio.Counter(board.IMU_INT1, edge=countio.Edge.RISE, pull=digitalio.Pull.DOWN) as interrupt:
        while True:
            if interrupt.count > 0:
                interrupt.count = 0
                event.set()
            await asyncio.sleep(0)

async def loop(event):
    ti = sp.ticks_ms()
    while True:
        await event.wait()
        event.clear()
        # print(sensor.gyro)
        print(f"time: {sp.ticks_ms() -ti}, gyro: {sensor.gyro}")
        await asyncio.sleep(0)

async def main():

    ev = asyncio.Event()
    await setup_imu()
    tasks = []
    tasks.append( asyncio.create_task( imu_interrupt(ev) ) )
    tasks.append( asyncio.create_task( loop(ev) ))
    await asyncio.gather(*tasks)
asyncio.run( main() )