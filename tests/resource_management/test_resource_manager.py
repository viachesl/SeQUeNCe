import math

import numpy

numpy.random.seed(0)

from sequence.components.memory import MemoryArray
from sequence.kernel.timeline import Timeline
from sequence.resource_management.resource_manager import *
from sequence.resource_management.rule_manager import Rule
from sequence.topology.node import Node


class FakeNode(Node):
    def __init__(self, name, tl):
        Node.__init__(self, name, tl)
        self.memory_array = MemoryArray(name + ".MemoryArray", tl)
        self.resource_manager = ResourceManager(self)
        self.send_log = []

    def send_message(self, dst: str, msg: "Message", priority=math.inf) -> None:
        self.send_log.append((dst, msg))

    def get_idle_memory(self, info):
        pass

class FakeProtocol():
    def __init__(self, name, memories=[]):
        self.name = name
        self.other_is_setted = False
        self.is_started = False
        self.rule = Rule(None, None, None)
        self.rule.protocols.append(self)
        self.memories = memories
        self.own = None

    def is_ready(self):
        return self.other_is_setted

    def set_others(self, other):
        self.other_is_setted = True

    def start(self):
        self.is_started = True


def test_load():
    def fake_condition(memo_info, manager):
        if memo_info.state == "RAW":
            return [memo_info]
        else:
            return []

    def fake_action(memories):
        return FakeProtocol("protocol"), [None], [None]

    tl = Timeline()
    node = FakeNode("node", tl)
    assert len(node.resource_manager.rule_manager) == 0
    rule = Rule(1, fake_action, fake_condition)
    for memo_info in node.resource_manager.memory_manager:
        assert memo_info.state == "RAW"
    node.resource_manager.load(rule)
    assert len(node.resource_manager.rule_manager) == 1
    for memo_info in node.resource_manager.memory_manager:
        assert memo_info.state == "OCCUPIED"
    assert len(node.resource_manager.waiting_protocols) == len(node.memory_array)
    assert len(node.resource_manager.pending_protocols) == 0
    assert len(rule.protocols) == len(node.memory_array)


def test_update():
    def fake_condition(memo_info, manager):
        if memo_info.state == "ENTANGLED" and memo_info.fidelity > 0.8:
            return [memo_info]
        else:
            return []

    def fake_action(memories):
        return FakeProtocol("protocol"), [None], [None]

    tl = Timeline()
    node = FakeNode("node", tl)
    assert len(node.resource_manager.rule_manager) == 0
    rule = Rule(1, fake_action, fake_condition)
    node.resource_manager.load(rule)
    assert len(node.resource_manager.rule_manager) == 1
    for memo_info in node.resource_manager.memory_manager:
        assert memo_info.state == "RAW"

    protocol = FakeProtocol("protocol1")
    node.protocols.append(protocol)
    node.memory_array[0].fidelity = 0.5
    node.memory_array[0].detach(node.memory_array)
    node.memory_array[0].attach(protocol)
    node.resource_manager.update(protocol, node.memory_array[0], "ENTANGLED")
    assert len(node.protocols) == len(rule.protocols) == 0
    assert len(node.memory_array[0]._observers) == 1
    assert node.resource_manager.memory_manager[0].state == "ENTANGLED"

    protocol = FakeProtocol("protocol2")
    node.protocols.append(protocol)
    node.memory_array[1].fidelity = 0.9
    node.memory_array[1].attach(protocol)
    node.resource_manager.update(protocol, node.memory_array[1], "ENTANGLED")
    assert len(node.resource_manager.waiting_protocols) == len(rule.protocols) == 1
    assert len(node.memory_array[1]._observers) == 2
    assert node.resource_manager.memory_manager[1].state == "OCCUPIED"


def test_send_request():
    tl = Timeline()
    node = FakeNode("node", tl)
    resource_manager = node.resource_manager
    assert len(node.send_log) == 0
    protocol = FakeProtocol("no_send")
    resource_manager.send_request(protocol, None, None)
    assert len(node.send_log) == 0
    assert protocol in resource_manager.waiting_protocols and len(resource_manager.pending_protocols) == 0
    assert protocol.own == node
    protocol = FakeProtocol("send")
    node.resource_manager.send_request(protocol, "dst_id", "req_condition_func")
    assert len(node.send_log) == 1
    assert protocol in resource_manager.pending_protocols and len(resource_manager.waiting_protocols) == 1
    assert protocol.own == node


def test_received_message():
    def true_fun(protocols):
        return protocols[0]

    def false_fun(protocols):
        return None

    tl = Timeline()
    node = FakeNode("node", tl)
    resource_manager = node.resource_manager

    # test receive REQUEST message
    protocol1 = FakeProtocol("waiting_protocol")
    resource_manager.waiting_protocols.append(protocol1)
    req_msg = ResourceManagerMessage(ResourceManagerMsgType.REQUEST, protocol="ini_protocol",
                                     req_condition_func=true_fun)
    resource_manager.received_message("sender", req_msg)
    assert protocol1 in node.protocols
    assert protocol1 not in resource_manager.waiting_protocols
    assert protocol1.other_is_setted and protocol1.is_started
    assert node.send_log[-1][0] == "sender"
    assert isinstance(node.send_log[-1][1], ResourceManagerMessage)
    assert node.send_log[-1][1].msg_type == ResourceManagerMsgType.RESPONSE
    assert node.send_log[-1][1].is_approved

    protocol1 = FakeProtocol("waiting_protocol")
    resource_manager.waiting_protocols.append(protocol1)
    req_msg = ResourceManagerMessage(ResourceManagerMsgType.REQUEST, protocol="ini_protocol",
                                     req_condition_func=false_fun)
    resource_manager.received_message("sender", req_msg)
    assert protocol1 not in node.protocols
    assert protocol1 in resource_manager.waiting_protocols
    assert not protocol1.other_is_setted and not protocol1.is_started
    assert node.send_log[-1][0] == "sender"
    assert isinstance(node.send_log[-1][1], ResourceManagerMessage)
    assert node.send_log[-1][1].msg_type == ResourceManagerMsgType.RESPONSE
    assert not node.send_log[-1][1].is_approved

    # test receive RESPONSE message: is_approved==False and is_approved==True
    protocol2 = FakeProtocol("pending_protocol")
    resource_manager.pending_protocols.append(protocol2)
    resp_msg = ResourceManagerMessage(ResourceManagerMsgType.RESPONSE, protocol=protocol2, is_approved=False,
                                      paired_protocol="paired_protocol")
    resource_manager.received_message("sender", resp_msg)
    assert protocol2 not in node.protocols
    assert protocol2 not in resource_manager.pending_protocols
    assert not protocol2.other_is_setted and not protocol2.is_started
    assert protocol2 not in protocol2.rule.protocols

    protocol2 = FakeProtocol("pending_protocol")
    resource_manager.pending_protocols.append(protocol2)
    resp_msg = ResourceManagerMessage(ResourceManagerMsgType.RESPONSE, protocol=protocol2, is_approved=True,
                                      paired_protocol="paired_protocol")
    resource_manager.received_message("sender", resp_msg)
    assert protocol2 in node.protocols
    assert protocol2 not in resource_manager.pending_protocols
    assert protocol2.other_is_setted and protocol2.is_started


def test_expire():
    tl = Timeline()
    node = FakeNode("node", tl)
    tl.init()
    for info in node.resource_manager.memory_manager:
        info.to_occupied()
    rule = Rule(0, None, None)
    for i in range(6):
        node.memory_array[i].detach(node.memory_array)
    p1 = FakeProtocol("waiting_protocol", [node.memory_array[0]])
    node.memory_array[0].attach(p1)
    p2 = FakeProtocol("pending_protocol", [node.memory_array[1]])
    node.memory_array[1].attach(p2)
    p3 = FakeProtocol("running_protocol", [node.memory_array[2]])
    node.memory_array[2].attach(p3)
    p4 = FakeProtocol("other_waiting_protocol", [node.memory_array[3]])
    node.memory_array[3].attach(p4)
    p5 = FakeProtocol("other_pending_protocol", [node.memory_array[4]])
    node.memory_array[4].attach(p5)
    p6 = FakeProtocol("other_running_protocol", [node.memory_array[5]])
    node.memory_array[5].attach(p6)
    for p in [p1, p2, p3]:
        p.rule = rule
        rule.protocols.append(p)
    node.resource_manager.rule_manager.load(rule)
    for p in [p3, p6]:
        node.protocols.append(p)
    for p in [p2, p5]:
        node.resource_manager.pending_protocols.append(p)
    for p in [p1, p4]:
        node.resource_manager.waiting_protocols.append(p)
    for i in range(6):
        assert node.resource_manager.memory_manager[i].state == "OCCUPIED"
    node.resource_manager.expire(rule)
    assert p1 not in node.resource_manager.waiting_protocols and p4 in node.resource_manager.waiting_protocols
    assert p2 not in node.resource_manager.pending_protocols
    assert p5 in node.resource_manager.pending_protocols
    assert p3 not in node.protocols and p6 in node.protocols
    for i in range(3):
        assert node.resource_manager.memory_manager[i].state == "RAW"

    for i in range(3, 6):
        assert node.resource_manager.memory_manager[i].state == "OCCUPIED"

    for i, memory in enumerate(node.memory_array):
        if i < 3:
            assert len(memory._observers) == 1 and isinstance(memory._observers.pop(), MemoryArray)
        elif i < 6:
            assert len(memory._observers) == 1 and isinstance(memory._observers.pop(), FakeProtocol)


def test_ResourceManager1():
    from sequence.components.optical_channel import ClassicalChannel, QuantumChannel
    from sequence.topology.node import BSMNode
    from sequence.entanglement_management.generation import EntanglementGenerationA

    class TestNode(Node):
        def __init__(self, name, tl):
            Node.__init__(self, name, tl)
            self.memory_array = MemoryArray(name + ".MemoryArray", tl, num_memories=50)
            self.memory_array.owner = self
            self.resource_manager = ResourceManager(self)

        def receive_message(self, src: str, msg: "Message") -> None:
            if msg.receiver == "resource_manager":
                self.resource_manager.received_message(src, msg)
            else:
                if msg.receiver is None:
                    matching = [p for p in self.protocols if type(p) == msg.protocol_type]
                    for p in matching:
                        p.received_message(src, msg)
                else:
                    for protocol in self.protocols:
                        if protocol.name == msg.receiver:
                            protocol.received_message(src, msg)
                            break

        def get_idle_memory(self, info):
            pass

    def eg_rule_condition(memory_info, manager):
        if memory_info.state == "RAW":
            return [memory_info]
        else:
            return []

    def eg_rule_action1(memories_info):
        def eg_req_func(protocols):
            for protocol in protocols:
                if isinstance(protocol, EntanglementGenerationA):
                    return protocol

        memories = [info.memory for info in memories_info]
        memory = memories[0]
        protocol = EntanglementGenerationA(None, "EGA." + memory.name, "mid_node", "node2", memory)
        protocol.primary = True
        return [protocol, ["node2"], [eg_req_func]]

    def eg_rule_action2(memories_info):
        memories = [info.memory for info in memories_info]
        memory = memories[0]
        protocol = EntanglementGenerationA(None, "EGA." + memory.name, "mid_node", "node1", memory)
        return [protocol, [None], [None]]

    tl = Timeline()

    node1, node2 = TestNode("node1", tl), TestNode("node2", tl)
    mid_node = BSMNode("mid_node", tl, [node1.name, node2.name])
    mid_node.bsm.detectors[0].efficiency = 1
    mid_node.bsm.detectors[1].efficiency = 1

    cc0 = ClassicalChannel("cc_n1_n2", tl, 0, 1e3)
    cc1 = ClassicalChannel("cc_n2_n1", tl, 0, 1e3)
    cc2 = ClassicalChannel("cc_n1_m", tl, 0, 1e3)
    cc3 = ClassicalChannel("cc_m_n1", tl, 0, 1e3)
    cc4 = ClassicalChannel("cc_n2_m", tl, 0, 1e3)
    cc5 = ClassicalChannel("cc_m_n2", tl, 0, 1e3)
    cc0.set_ends(node1, node2)
    cc1.set_ends(node2, node1)
    cc2.set_ends(node1, mid_node)
    cc3.set_ends(mid_node, node1)
    cc4.set_ends(node2, mid_node)
    cc5.set_ends(mid_node, node2)

    qc0 = QuantumChannel("qc_n1_m", tl, 0, 1e3, frequency=8e7)
    qc1 = QuantumChannel("qc_n2_m", tl, 0, 1e3, frequency=8e7)
    qc0.set_ends(node1, mid_node)
    qc1.set_ends(node2, mid_node)

    tl.init()
    rule1 = Rule(10, eg_rule_action1, eg_rule_condition)
    node1.resource_manager.load(rule1)
    rule2 = Rule(10, eg_rule_action2, eg_rule_condition)
    node2.resource_manager.load(rule2)

    tl.run()

    for info in node1.resource_manager.memory_manager:
        print(info.memory.name, info.state, info.remote_memo)
    
    for info in node2.resource_manager.memory_manager:
        print(info.memory.name, info.state, info.remote_memo)

    for event in tl.events:
        print(event._is_removed, event.time, event.process.owner, event.process.activation)

    for info in node1.resource_manager.memory_manager:
        assert info.state == "ENTANGLED"

    for info in node1.resource_manager.memory_manager:
        for info2 in node2.resource_manager.memory_manager:
            if info.remote_memo == info2.memory.name:
                assert info2.remote_memo == info.memory.name
                break


def test_ResourceManager2():
    from sequence.kernel.process import Process
    from sequence.kernel.event import Event
    from sequence.components.optical_channel import ClassicalChannel, QuantumChannel
    from sequence.topology.node import BSMNode
    from sequence.entanglement_management.generation import EntanglementGenerationA

    class TestNode(Node):
        def __init__(self, name, tl):
            Node.__init__(self, name, tl)
            self.memory_array = MemoryArray(name + ".MemoryArray", tl, num_memories=50)
            self.memory_array.owner = self
            self.resource_manager = ResourceManager(self)

        def receive_message(self, src: str, msg: "Message") -> None:
            if msg.receiver == "resource_manager":
                self.resource_manager.received_message(src, msg)
            else:
                if msg.receiver is None:
                    matching = [p for p in self.protocols if type(p) == msg.protocol_type]
                    for p in matching:
                        p.received_message(src, msg)
                else:
                    for protocol in self.protocols:
                        if protocol.name == msg.receiver:
                            protocol.received_message(src, msg)
                            break

        def get_idle_memory(self, info):
            pass

    def eg_rule_condition(memory_info, manager):
        if memory_info.state == "RAW":
            return [memory_info]
        else:
            return []

    def eg_rule_action1(memories_info):
        def eg_req_func(protocols):
            for protocol in protocols:
                if isinstance(protocol, EntanglementGenerationA):
                    return protocol

        memories = [info.memory for info in memories_info]
        memory = memories[0]
        protocol = EntanglementGenerationA(None, "EGA." + memory.name, "mid_node", "node2", memory)
        protocol.primary = True
        return [protocol, ["node2"], [eg_req_func]]

    def eg_rule_action2(memories_info):
        memories = [info.memory for info in memories_info]
        memory = memories[0]
        protocol = EntanglementGenerationA(None, "EGA." + memory.name, "mid_node", "node1", memory)
        return [protocol, [None], [None]]

    tl = Timeline()

    node1, node2 = TestNode("node1", tl), TestNode("node2", tl)
    mid_node = BSMNode("mid_node", tl, [node1.name, node2.name])
    mid_node.bsm.detectors[0].efficiency = 1
    mid_node.bsm.detectors[1].efficiency = 1

    cc0 = ClassicalChannel("cc_n1_n2", tl, 0, 1e3)
    cc1 = ClassicalChannel("cc_n2_n1", tl, 0, 1e3)
    cc2 = ClassicalChannel("cc_n1_m", tl, 0, 1e3)
    cc3 = ClassicalChannel("cc_m_n1", tl, 0, 1e3)
    cc4 = ClassicalChannel("cc_n2_m", tl, 0, 1e3)
    cc5 = ClassicalChannel("cc_m_n2", tl, 0, 1e3)
    cc0.set_ends(node1, node2)
    cc1.set_ends(node2, node1)
    cc2.set_ends(node1, mid_node)
    cc3.set_ends(mid_node, node1)
    cc4.set_ends(node2, mid_node)
    cc5.set_ends(mid_node, node2)

    qc0 = QuantumChannel("qc_n1_m", tl, 0, 1e3, frequency=8e7)
    qc1 = QuantumChannel("qc_n2_m", tl, 0, 1e3, frequency=8e7)
    qc0.set_ends(node1, mid_node)
    qc1.set_ends(node2, mid_node)

    tl.init()
    rule1 = Rule(10, eg_rule_action1, eg_rule_condition)
    node1.resource_manager.load(rule1)
    rule2 = Rule(10, eg_rule_action2, eg_rule_condition)
    node2.resource_manager.load(rule2)

    process = Process(node1.resource_manager, "expire", [rule1])
    event = Event(10, process)
    tl.schedule(event)

    process = Process(node2.resource_manager, "expire", [rule2])
    event = Event(10, process)
    tl.schedule(event)

    tl.run()

    # for info in node1.resource_manager.memory_manager:
    #     print(info.memory.name, info.state, info.remote_memo)
    #
    # for info in node2.resource_manager.memory_manager:
    #     print(info.memory.name, info.state, info.remote_memo)

    for info in node1.resource_manager.memory_manager:
        assert info.state == "RAW"

    for info in node2.resource_manager.memory_manager:
        assert info.state == "RAW"

    assert len(node1.protocols) == len(node2.protocols) == 0
    assert len(node1.resource_manager.pending_protocols) == len(node2.resource_manager.pending_protocols) == 0
    assert len(node1.resource_manager.waiting_protocols) == len(node2.resource_manager.waiting_protocols) == 0
