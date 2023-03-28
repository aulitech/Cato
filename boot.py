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
import supervisor

# False -> Writable for CircuitPython
# True  -> Writable for Computer

class CHMOD:
    COMP    = True  #board computer writable
    BOARD   = False #board self writable
    USR_DEF = mc.nvm[0] # board to user defined
    def to_board():
        storage.remount("/", CHMOD.BOARD)

    def to_comp():
        storage.remount("/", CHMOD.COMP)

def rename_usb_mnt(name = "auli_cato"):
    m = storage.getmount("/")
    m.label = name

def check_config():
    config_exists = True
    try: 
        with open("config.json", "r") as j:
            print("Config exists")
    except OSError:
        config_exists = False
        print("Config does not exist.")
    return config_exists

# def write_default_config():
    
#     config = {}
#     st_mat = None

#     try:
#         with open("config.json", 'r') as cfg:
#             config = json.load(cfg)
#     except OSError:
#         print("config doesn't exist - creating file")
#         with open("config.json", 'x') as cfg:
#             print("Created New (Empty) config.json")
    
#     print("Attempting to open st_matrix")
#     with open("st_matrix.json", 'r') as st:
#         st_mat = json.load(st)
        

#     config['st_matrix'] = st_mat

#     with open("config.json", "w") as f:
#         print('config')
#         json.dump(config, f)

def refresh_data_folder():
    # data_001, data 002, ...

    # get existign data num
    num = 1
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


def main():
    CHMOD.to_board() # remounts storage as board writable
    rename_usb_mnt() # renames usb

    has_config = check_config()
    print(f"Checking config: {has_config}")
    #print("USB?",supervisor.runtime.usb_connected)

    storage.remount("/", True)
    os.sync()

if __name__ == "__main__":
    main()
