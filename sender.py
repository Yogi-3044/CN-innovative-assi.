class Sender:
    def __init__(self, total_frames, window_size, timeout_ms):
        self.total = total_frames
        self.window = window_size
        self.timeout = timeout_ms

        self.base = 0          # oldest frame that is not yet acknowledged
        self.next_seq = 0      # next new frame to send
        self.acked = [False] * total_frames        # individual ACK status
        self.sent = [False] * total_frames         # has the frame been sent at least once?
        self.timer_start = [0.0] * total_frames    # time the frame was last (re)sent

    def can_send_new(self):
        """A new frame may be sent only if it lies inside the sending window."""
        return self.next_seq < self.total and self.next_seq < self.base + self.window

    def send_new(self, now):
        seq = self.next_seq
        self.sent[seq] = True
        self.timer_start[seq] = now      # start the timer of this frame
        self.next_seq += 1
        return seq

    def restart_timer(self, seq, now):
        self.timer_start[seq] = now

    def timed_out_frames(self, now):
        """Frames sent but not acknowledged whose own timer has expired."""
        result = []
        for seq in range(self.base, self.next_seq):
            if not self.acked[seq] and now - self.timer_start[seq] >= self.timeout:
                result.append(seq)
        return result

    def receive_ack(self, seq):
        """Mark ONE frame as acknowledged and slide the window if possible.
        Returns False if the ACK was a duplicate (or invalid)."""
        if seq < 0 or seq >= self.total or self.acked[seq]:
            return False
        self.acked[seq] = True
        # slide the window over all consecutive acknowledged frames
        while self.base < self.total and self.acked[self.base]:
            self.base += 1
        return True

    def all_acked(self):
        return self.base == self.total

    def status(self, seq):
        """Used by the GUI: 'acked', 'sent' (unacknowledged) or 'new'."""
        if self.acked[seq]:
            return "acked"
        if self.sent[seq]:
            return "sent"
        return "new"