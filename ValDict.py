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

    def dump(self):
        try:
            with open("config.json", "w") as f:
                json.dump(self.d, f)
        except Exception as e:
            print(f"Not self-writable - {e} in ValDict.dump")


config = {}
with open("config.json",'r') as f:
    config = ValDict(json.load(f))
