import asyncio
from MinPointer import MinPointer

async def main():
    mp = MinPointer()
    mp.imu.imu_enable.set()
    mp.mouse_ena.set()
    mp.imu.spark()
    await asyncio.gather(*mp.tasks.values())

asyncio.run(main())