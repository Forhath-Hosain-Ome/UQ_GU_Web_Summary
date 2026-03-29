class POState:
    def __init__(self, pos_list=None):
        self.pos_list = pos_list or []
        self.index = 0

    def next(self):
        if self.index < len(self.pos_list):
            value = str(self.pos_list[self.index])
            self.index += 1
            return value
        return ""