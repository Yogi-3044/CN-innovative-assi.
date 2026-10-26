class Receiver:
    def __init__(self, total_frames, window_size):
        self.total = total_frames
        self.window = window_size
        self.rcv_base = 0        # next frame that must be delivered (in order)
        self.buffer = set()      # frames received and waiting for delivery
        self.delivered = []      # frames already delivered, in order
        self.duplicates = 0

    def receive(self, seq):
        """Process one correct (uncorrupted) frame.
        Returns (ack_seq or None, messages before the ACK, messages after the ACK)."""
        before = []
        after = []
        ack = None

        if self.rcv_base <= seq < self.rcv_base + self.window:
            # frame lies inside the receiving window -> accept it
            if seq in self.buffer:
                self.duplicates += 1
                before.append(("Frame %d is a duplicate (already buffered) - ignored" % seq, "dup"))
            elif seq == self.rcv_base:
                before.append(("Frame %d received in order" % seq, "recv"))
                self.buffer.add(seq)
            else:
                before.append(("Frame %d received out of order" % seq, "recv"))
                self.buffer.add(seq)
                before.append(("Frame %d buffered" % seq, "buffer"))
            ack = seq   # every accepted frame gets its own ACK

            # deliver every consecutive frame starting from rcv_base
            while self.rcv_base in self.buffer:
                x = self.rcv_base
                self.buffer.remove(x)
                self.delivered.append(x)
                if x == seq:
                    after.append(("Frame %d delivered" % x, "deliver"))
                else:
                    after.append(("Buffered Frame %d delivered" % x, "deliver"))
                self.rcv_base += 1

        elif self.rcv_base - self.window <= seq < self.rcv_base:
            # frame was already delivered earlier (our ACK was probably lost):
            # discard it but send the ACK again
            self.duplicates += 1
            before.append(("Frame %d is a duplicate (already delivered) - ACK sent again" % seq, "dup"))
            ack = seq

        else:
            before.append(("Frame %d is outside the receiver window - discarded" % seq, "dup"))

        return ack, before, after