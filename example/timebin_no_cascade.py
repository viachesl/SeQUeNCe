from numpy import random
from pathlib import Path
import math
import statistics

import sequence
from sequence.kernel.event import Event
from sequence.kernel.process import Process
from sequence.kernel.timeline import Timeline
from sequence.protocols.qkd.BB84 import *
from sequence.components.optical_channel import *
from sequence.topology.node import *
from sequence.utils.encoding import *


if __name__ == "__main__":
    random.seed(1)

    runtime = 1e12
    dark_count = 425
    distances = [1]
    # distances = [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]  # distances in km
    errors = []  # store error rates
    throughputs = []  # store throughputs
    latencies = []  # store latencies

    # open file to store experiment results
    Path("results/timebin").mkdir(parents=True, exist_ok=True)
    filename = "results/timebin/distance_no_cascade.log"
    fh = open(filename, 'w')

    for distance in distances:
        tl = Timeline(runtime)
        qc = QuantumChannel("qc", tl, distance=distance * 1e3, attenuation=0.0002)
        cc = ClassicalChannel("cc", tl, distance=distance * 1e3)

        # Alice
        ls_params = {"frequency": 2e6, "mean_photon_num": 0.1}
        alice = QKDNode("alice", tl, encoding=time_bin, stack_size=1)
        
        for name, param in ls_params.items():
            alice.update_lightsource_params(name, param)

        # Bob
        detector_params = [{"efficiency": 0.072, "dark_count": dark_count, "time_resolution": 10},
                           {"efficiency": 0.072, "dark_count": dark_count, "time_resolution": 10},
                           {"efficiency": 0.072, "dark_count": dark_count, "time_resolution": 10}]
        bob = QKDNode("bob", tl, encoding=time_bin, stack_size=1)

        for i in range(len(detector_params)):
            for name, param in detector_params[i].items():
                bob.update_detector_params(i, name, param)

        qc.set_ends(alice, bob)
        cc.set_ends(alice, bob)
        
        # BB84
        pair_bb84_protocols(alice.protocol_stack[0], bob.protocol_stack[0])

        process = Process(alice.protocol_stack[0], "push", [256, 10, math.inf])
        event = Event(0, process)
        tl.schedule(event)

        tl.init()
        tl.run()

        bba = alice.protocol_stack[0]

        error = statistics.mean(bba.error_rates)
        throughput = statistics.mean(bba.throughputs)
        latency = bba.latency

        print("{} km:".format(distance))
        print("\tbb84 error:\t\t\t{}".format(error))
        print("\tbb84 throughput:\t{}".format(throughput))

        errors.append(error)
        throughputs.append(throughput)
        latencies.append(latency)

        fh.write(str(distance))
        fh.write(' ')
        fh.write(str(error))
        fh.write(' ')
        fh.write(str(throughput))
        fh.write(' ')
        fh.write(str(latency))
        fh.write('\n')

    print(errors)
    print(throughputs)
    print(latencies)
