# Cato/boot.py
'''
If you are here, you probably are wondering how to unlock the board once you have set it to be read-only by your computer.
The command you want is in circuitpython REPL:
    import storage
    storage.erase_filesystem()
Then close serial monitor
    erase file system never finishes afaik
Now make changes to code or boot
    > for continually editable code use storage.remount("/", True)
Then run the script
    scripts/copy_all_to_board.sh
Then unplug the board, and reconnect the board. 
    Reopen Serial Monitor
'''
import os
import storage
import json
import microcontroller as mc

# False -> Writable for CircuitPython
# True  -> Writable for Computer
# at time of boot, decide whether we're in 

storage.remount("/", False)

os.sync()

new_name = "auli_cato"
m = storage.getmount("/")
m.label = new_name
config = {
    "device" : {
        "name": "Cato",
        "activated":"",
        "lastused": "",
        "lastboot": "",
        "firmwareVersion":"",
        "computer_write_enabled_on_boot":mc.nvm[0]
    },
    "connections" :  [
        {
            "name":"",
            "ble": "", 
            "calibration":"" 
        },
        {
            "name":"",
            "ble":"",
            "calibration":""
        }
    ]
}

print("Attempting to read config.json")
try: 
    with open("config.json", "r") as j:
        print("Read File Successfully.")
except OSError:
    print("File does not exist.")
    try:
        with open("config.json", "x") as j:
            print("config.json created")
            j.close()
            try:
                with open("config.json", "w") as j:
                    j.write(json.dumps(config))
                    j.close()
            except:
                print("config file write error")
    except:
        print("config file creation Error")

os.sync()

try:
    os.rmdir("/data")
    print("/data deleted")
except:
    print("Error removing /data")
try:
    os.mkdir("/data")
    print("/data created")
except:
    print("Did not make new data directory")

print("Board is computer writable: {}".format(True if mc.nvm[0] else False))

storage.remount("/", mc.nvm[0])
os.sync()
