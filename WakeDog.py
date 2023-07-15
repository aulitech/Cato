import asyncio

# this import causes malloc issues
# from StrUUIDService import DebugStream

# This class is like a watchdog, but will monitor Cato and help it go to sleep and wake up.
class WakeDog:
    max_time = 20
    curr_time = 0
    def feed():
        WakeDog.curr_time = 0
    
    async def tick():
        while True:
            await asyncio.sleep(1)
            WakeDog.curr_time += 1
            if(WakeDog.curr_time % 5 == 0 and WakeDog.curr_time >= WakeDog.max_time / 2):

                pass
                print(f"Sleep Timer (WakeDog) {WakeDog.curr_time} / {WakeDog.max_time}")
        
    async def watch():
        from Cato import Events
        while True:
            #DebugStream.println("watching")
            await asyncio.sleep(0)
            if( WakeDog.curr_time >= WakeDog.max_time):
                Events.sleep.set()
    
    tasks = {
        "tick" : asyncio.create_task(tick()),
        "watch": asyncio.create_task(watch())
    }