# protocol.py - ties sender, receiver and channel together (no GUI code here)
import random
from channel import Channel, OK, LOST, CORRUPT
from sender import Sender
from receiver import Receiver

LINGER_MS = 700   # how long a lost/corrupted packet stays visible


class Packet:
    """A frame (DATA) or an acknowledgement (ACK) travelling through the channel."""

    def __init__(self, kind, seq, start, duration, fate, retransmit=False):
        self.kind = kind              # "DATA" or "ACK"
        self.seq = seq
        self.start = start
        self.duration = duration
        self.fate = fate              # ok / lost / corrupt
        self.retransmit = retransmit
        # a lost packet disappears somewhere in the middle of the channel
        self.drop_at = random.uniform(0.35, 0.75) if fate == LOST else 1.0
        self.end_time = start + duration * self.drop_at
        self.handled = False          # has it reached its end point yet?
        self.handled_time = 0.0

    def progress(self, now):
        p = (now - self.start) / self.duration
        return max(0.0, min(p, self.drop_at))


class Stats:
    def __init__(self):
        self.sent = 0              # all frame transmissions (including retransmissions)
        self.retransmissions = 0
        self.lost = 0
        self.corrupted = 0
        self.acks_sent = 0
        self.acks_received = 0
        self.acks_lost = 0
        self.timeouts = 0


class Simulation:
    def __init__(self, total_frames, window_size, loss_prob, corrupt_prob, delay_ms):
        self.total = total_frames
        self.window = window_size
        self.delay = delay_ms                      # time a packet needs to cross the channel
        self.send_interval = delay_ms / 4.0        # gap between two new frames
        self.timeout = 2 * delay_ms + 400          # a bit more than one round trip

        self.now = 0.0                             # simulated time in milliseconds
        self.channel = Channel(loss_prob, corrupt_prob)
        self.sender = Sender(total_frames, window_size, self.timeout)
        self.receiver = Receiver(total_frames, window_size)
        self.stats = Stats()

        self.packets = []         # packets currently drawn on the channel
        self.events = []          # new log lines, the GUI reads and clears this list
        self.last_send_time = -1e9
        self.done = False

    def log(self, text, tag):
        self.events.append((self.now, text, tag))

    # ---------------------------------------------------------------
    def step(self, dt):
        """Advance the simulation by dt milliseconds."""
        if self.done:
            return
        self.now += dt
        self.process_arrivals()
        self.check_timeouts()
        self.send_new_frame()
        self.remove_old_packets()
        if self.sender.all_acked():
            self.done = True
            self.log("All %d frames delivered reliably - simulation complete" % self.total, "info")

    # ---------------------------------------------------------------
    def transmit_frame(self, seq, retransmit):
        fate = self.channel.decide()
        self.packets.append(Packet("DATA", seq, self.now, self.delay, fate, retransmit))
        self.stats.sent += 1
        if retransmit:
            self.stats.retransmissions += 1
            self.log("Frame %d retransmitted" % seq, "retx")
        else:
            self.log("Frame %d sent" % seq, "send")

    def send_ack(self, seq):
        fate = self.channel.decide()
        self.packets.append(Packet("ACK", seq, self.now, self.delay, fate))
        self.stats.acks_sent += 1
        self.log("ACK %d sent" % seq, "ack")

    def send_new_frame(self):
        if self.sender.can_send_new() and self.now - self.last_send_time >= self.send_interval:
            seq = self.sender.send_new(self.now)
            self.last_send_time = self.now
            self.transmit_frame(seq, False)

    def check_timeouts(self):
        for seq in self.sender.timed_out_frames(self.now):
            self.stats.timeouts += 1
            self.log("Timeout for Frame %d" % seq, "timeout")
            self.sender.restart_timer(seq, self.now)
            self.transmit_frame(seq, True)      # only THIS frame is resent

    # ---------------------------------------------------------------
    def process_arrivals(self):
        for p in list(self.packets):
            if p.handled or self.now < p.end_time:
                continue
            p.handled = True
            p.handled_time = self.now
            if p.kind == "DATA":
                self.frame_reached_end(p)
            else:
                self.ack_reached_end(p)

    def frame_reached_end(self, p):
        seq = p.seq
        if p.fate == LOST:
            self.stats.lost += 1
            self.log("Frame %d lost in the channel" % seq, "lost")
        elif p.fate == CORRUPT:
            self.stats.corrupted += 1
            self.log("Frame %d arrived corrupted - receiver discards it" % seq, "corrupt")
        else:
            ack, before, after = self.receiver.receive(seq)
            self.log("Frame %d received" % seq, "recv")
            for text, tag in before:
                self.log(text, tag)
            if ack is not None:
                self.send_ack(ack)
            for text, tag in after:
                self.log(text, tag)

    def ack_reached_end(self, p):
        seq = p.seq
        if p.fate == LOST:
            self.stats.acks_lost += 1
            self.log("ACK %d lost in the channel" % seq, "lost")
        elif p.fate == CORRUPT:
            self.log("ACK %d corrupted - sender discards it" % seq, "corrupt")
        else:
            self.stats.acks_received += 1
            old_base = self.sender.base
            is_new = self.sender.receive_ack(seq)
            if is_new:
                self.log("ACK %d received" % seq, "ack")
                if self.sender.base != old_base:
                    self.log("Sender window slides: base %d -> %d" % (old_base, self.sender.base), "info")
            else:
                self.log("ACK %d received again (duplicate) - ignored" % seq, "dup")

    def remove_old_packets(self):
        keep = []
        for p in self.packets:
            if p.handled and (p.fate == OK or self.now - p.handled_time > LINGER_MS):
                continue
            keep.append(p)
        self.packets = keep