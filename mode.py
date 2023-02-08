import microcontroller as mc

def comp_writable():
    mc.nvm[0] = True
    mc.reset()

def self_writable():
    mc.nvm[0] = False
    mc.reset()