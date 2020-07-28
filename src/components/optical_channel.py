import heapq as hq
from typing import TYPE_CHECKING

from numpy import random

if TYPE_CHECKING:
    from ..kernel.timeline import Timeline
    from ..topology.node import Node
    from ..components.photon import Photon
    from ..message import Message

from ..kernel.entity import Entity
from ..kernel.event import Event
from ..kernel.process import Process


class OpticalChannel(Entity):
    def __init__(self, name: str, timeline: "Timeline", attenuation: float, distance: int, polarization_fidelity: float, light_speed: float):
        Entity.__init__(self, name, timeline)
        self.ends = []
        self.attenuation = attenuation
        self.distance = distance  # (measured in m)
        self.polarization_fidelity = polarization_fidelity
        self.light_speed = light_speed # used for photon timing calculations (measured in m/ps)
        # self.chromatic_dispersion = kwargs.get("cd", 17)  # measured in ps / (nm * km)

    def init(self) -> None:
        pass

    def set_distance(self, distance: int) -> None:
        self.distance = distance


class QuantumChannel(OpticalChannel):
    def __init__(self, name: str, timeline: "Timeline", attenuation: float, distance: int, polarization_fidelity=1, light_speed=2e-4, frequency=8e7):
        super().__init__(name, timeline, attenuation, distance, polarization_fidelity, light_speed)
        self.delay = 0
        self.loss = 1
        self.frequency = frequency # maximum frequency for sending qubits (measured in Hz)
        self.send_bins = []

    def init(self) -> None:
        self.delay = round(self.distance / self.light_speed)
        self.loss = 1 - 10 ** (self.distance * self.attenuation / -10)

    def set_ends(self, end1: "Node", end2: "Node") -> None:
        self.ends.append(end1)
        self.ends.append(end2)
        end1.assign_qchannel(self, end2.name)
        end2.assign_qchannel(self, end1.name)

    def transmit(self, qubit: "Photon", source: "Node") -> None:
        assert self.delay != 0 and self.loss != 1, "QuantumChannel init() function has not been run for {}".format(self.name)

        # remove lowest time bin
        if len(self.send_bins) > 0:
            time = -1
            while time < self.timeline.now():
                time_bin = hq.heappop(self.send_bins)
                time = int(time_bin * (1e12 / self.frequency))
            assert time == self.timeline.now(), "qc {} transmit method called at invalid time".format(self.name)

        # check if photon kept
        if (random.random_sample() > self.loss) or qubit.is_null:
            if source not in self.ends:
                raise Exception("no endpoint", source)

            receiver = None
            for e in self.ends:
                if e != source:
                    receiver = e

            # check if polarization encoding and apply necessary noise
            if (qubit.encoding_type["name"] == "polarization") and (
                    random.random_sample() > self.polarization_fidelity):
                qubit.random_noise()

            # schedule receiving node to receive photon at future time determined by light speed
            future_time = self.timeline.now() + self.delay
            process = Process(receiver, "receive_qubit", [source.name, qubit])
            event = Event(future_time, process)
            self.timeline.schedule(event)

        # if photon lost, exit
        else:
            pass

    def schedule_transmit(self, min_time: int) -> int:
        min_time = max(min_time, self.timeline.now())
        time_bin = min_time * (self.frequency / 1e12)
        if time_bin - int(time_bin) > 0.00001:
            time_bin = int(time_bin) + 1
        else:
            time_bin = int(time_bin)

        # find earliest available time bin
        while time_bin in self.send_bins:
            time_bin += 1
        hq.heappush(self.send_bins, time_bin)

        # calculate time
        time = int(time_bin * (1e12 / self.frequency))
        return time


class ClassicalChannel(OpticalChannel):
    def __init__(self, name: str, timeline: "Timeline", distance: int, delay=-1):
        super().__init__(name, timeline, 0, distance, 0, 2e-4)
        if delay == -1:
            self.delay = distance / self.light_speed
        else:
            self.delay = delay

    def set_ends(self, end1: "Node", end2: "Node") -> None:
        self.ends.append(end1)
        self.ends.append(end2)
        end1.assign_cchannel(self, end2.name)
        end2.assign_cchannel(self, end1.name)

    def transmit(self, message: "Message", source: "Node", priority: int) -> None:
        # get node that's not equal to source
        if source not in self.ends:
            raise Exception("no endpoint", source)

        receiver = None
        for e in self.ends:
            if e != source:
                receiver = e

        future_time = int(round(self.timeline.now() + int(self.delay)))
        process = Process(receiver, "receive_message", [source.name, message])
        event = Event(future_time, process, priority)
        self.timeline.schedule(event)