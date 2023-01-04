import asyncio

async def loop_on_timer(ev):
    while True:
        print("looped on timer")
        await asyncio.sleep(3)
        ev.set()

async def loop_on_event(ev):
    while True:
        print("awaiting")
        await ev.wait()
        print("got my event")
        ev.clear()

async def main():
    ev = asyncio.Event()

    tasks = [
        asyncio.create_task( loop_on_timer(ev) ),
        asyncio.create_task( loop_on_event(ev) )
    ]

    asyncio.gather( *tasks )

asyncio.run( main() )