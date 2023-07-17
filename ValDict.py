import json


class ValDict(object):

    def __init__(self, d : dict = {}):
        self.d = d
    
    def __getitem__(self, key):
        val = self.d[key]["value"]
        if(isinstance(val,dict)):
            val = ValDict(val)
        return val
    
    def __setitem__(self, key, val):
        self.d[key]["value"] = val


config = {}
with open("config.json",'r') as f:
    config = ValDict(json.load(f))
config = config.d