import random

OK = "ok"
LOST = "lost"
CORRUPT = "corrupt"

class Channel:
    """Randomly decides what happens to every frame / ACK that enters it."""

    def __init__(self, loss_prob, corrupt_prob):
        self.loss_prob = loss_prob        
        self.corrupt_prob = corrupt_prob  

    def decide(self):
        r = random.random()
        if r < self.loss_prob:
            return LOST
        if r < self.loss_prob + self.corrupt_prob:
            return CORRUPT
        return OK