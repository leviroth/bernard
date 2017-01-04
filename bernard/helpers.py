def deserialize_thing_id(self, thing_id):
    return tuple(int(x, base=36) for x in thing_id[1:].split('_'))
