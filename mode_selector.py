# for ./ execution use: "#! /c/Users/finnb/AppData/Local/Programs/Python/Python310/python"
import time
import microcontroller as mc

boot_timer = 3

def countdown(timer = boot_timer):
    for i in range(timer):
        print('\t', timer - i)
        time.sleep(1)

def to_computer_writable():
    mc.nvm[0] = True
    print("\nMicrocontroller.nvm[0] -> True")
    print("Rebooting into computer writable mode in {} seconds. For self-writable hit CtrC again".format(boot_timer))
    try:
        countdown()
    except KeyboardInterrupt:
        return
    mc.reset()

def to_self_writable():
    mc.nvm[0] = False
    print("\nMicrocontroller.nvm[0] -> False")
    print("Rebooting into self writable mode in {} seconds. For computer-writable hit CtrC again".format(boot_timer))
    try:
        countdown()
    except KeyboardInterrupt:
        return
    mc.reset()

def select_reboot_mode():
    print("\n======== BOOT MODE SELECTION ========\n")
    while True:    
        print("Reboot mode?:")
        print("\t0: Computer Writable")
        print("\t1: Self-Writable")
        print("\t2: REPL (or hit Ctr+C)")
        print("INPUT:\t", end='')
        my_str = input()  # type and press ENTER/RETURN
        if my_str=="0":
            to_computer_writable()
        elif my_str == "1":
            to_self_writable()
        elif my_str == "2":
            break
        else:
            print("\tInput not recognized.\n")
