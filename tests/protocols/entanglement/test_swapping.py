import numpy
import pytest
from sequence.components.memory import AtomMemory
from sequence.components.optical_channel import ClassicalChannel
from sequence.kernel.timeline import Timeline
from sequence.protocols.entanglement.swapping import *
from sequence.topology.node import Node

numpy.random.seed(0)


class ResourceManager():
    def __init__(self):
        self.log = []

    def update(self, memory, state):
        self.log.append((memory, state))


class FakeNode(Node):
    def __init__(self, name, tl, **kwargs):
        Node.__init__(self, name, tl)
        self.msg_log = []
        self.resource_manager = ResourceManager()

    def receive_message(self, src: str, msg: "Message"):
        self.msg_log.append((self.timeline.now(), src, msg))
        for protocol in self.protocols:
            if protocol.name == msg.receiver:
                protocol.received_message(src, msg)


def test_EntanglementSwappingMessage():
    # __init__ function
    msg = EntanglementSwappingMessage("SWAP_RES", "receiver", fidelity=0.9, remote_node="a1", remote_memo=2)
    assert ((msg.msg_type == "SWAP_RES") and
            msg.receiver == "receiver" and
            (msg.fidelity == 0.9) and
            (msg.remote_node == "a1") and
            (msg.remote_memo == 2))
    with pytest.raises(Exception):
        EntanglementSwappingMessage("error")


def test_EntanglementSwapping():
    tl = Timeline()
    a1 = FakeNode("a1", tl)
    a2 = FakeNode("a2", tl)
    a3 = FakeNode("a3", tl)
    cc1 = ClassicalChannel("a1-a2", tl, 0, 1e5)
    cc1.set_ends(a1, a2)
    cc1 = ClassicalChannel("a2-a3", tl, 0, 1e5)
    cc1.set_ends(a2, a3)
    tl.init()
    counter1 = counter2 = 0

    for i in range(1000):
        memo1 = AtomMemory("a1.%d" % i, timeline=tl, fidelity=0.9)
        memo2 = AtomMemory("a2.%d" % i, timeline=tl, fidelity=0.9)
        memo3 = AtomMemory("a2.%d" % i, timeline=tl, fidelity=0.9)
        memo4 = AtomMemory("a3.%d" % i, timeline=tl, fidelity=0.9)

        memo1.entangled_memory["node_id"] = "a2"
        memo1.entangled_memory["memo_id"] = memo2.name
        memo2.entangled_memory["node_id"] = "a1"
        memo2.entangled_memory["memo_id"] = memo1.name
        memo3.entangled_memory["node_id"] = "a3"
        memo3.entangled_memory["memo_id"] = memo4.name
        memo4.entangled_memory["node_id"] = "a2"
        memo4.entangled_memory["memo_id"] = memo3.name

        es1 = EntanglementSwappingB(a1, "a1.ESb%d" % i, memo1)
        es2 = EntanglementSwappingA(a2, "a2.ESa%d" % i, memo2, memo3, success_prob=0.5)
        es3 = EntanglementSwappingB(a3, "a3.ESb%d" % i, memo4)

        es1.set_another(es2)
        es2.set_others(es1, es3)
        es3.set_another(es2)

        es2.start()

        assert memo2.fidelity == memo3.fidelity == 0
        assert memo1.entangled_memory["node_id"] == memo4.entangled_memory["node_id"] == "a2"
        assert memo2.entangled_memory["node_id"] == memo3.entangled_memory["node_id"] == None
        assert memo2.entangled_memory["memo_id"] == memo3.entangled_memory["memo_id"] == None
        assert a2.resource_manager.log[-2] == (memo2, "EMPTY")
        assert a2.resource_manager.log[-1] == (memo3, "EMPTY")

        tl.run()

        if es2.is_success:
            counter1 += 1
            assert memo1.entangled_memory["node_id"] == "a3" and memo4.entangled_memory["node_id"] == "a1"
            assert memo1.fidelity == memo4.fidelity > 0
            assert a1.resource_manager.log[-1] == (memo1, "ENTANGLE")
            assert a3.resource_manager.log[-1] == (memo4, "ENTANGLE")
        else:
            counter2 += 1
            assert memo1.entangled_memory["node_id"] == memo4.entangled_memory["node_id"] == None
            assert memo1.fidelity == memo4.fidelity == 0
            assert a1.resource_manager.log[-1] == (memo1, "EMPTY")
            assert a3.resource_manager.log[-1] == (memo4, "EMPTY")

    assert abs((counter1 / counter2) - 1) - 1 < 0.1
