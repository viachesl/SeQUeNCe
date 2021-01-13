from collections import defaultdict
from socket import socket
from pickle import loads, dumps
from typing import List
from time import time

from .quantum_manager_server import generate_arg_parser, QuantumManagerMsgType, QuantumManagerMessage
from ..components.circuit import Circuit


class QuantumManagerClient():
    """Class to pocess interactions with multiprocessing quantum manager server.

    Unless otherwise noted, the operation of all functions are the same as those of the QuantumManagerClass.

    Attributes:
        s (socket): socket for communication with server.
    """

    def __init__(self, formalism: str, ip: str, port: int):
        """Constructor for QuantumManagerClient class.

        Args:
            ip: ip of quantum manager server.
            port: port of quantum manager server.
        """
        self.formalism = formalism
        self.s = socket()
        self.s.connect((ip, port))
        self.io_time = defaultdict(lambda: 0)
        self.type_counter = defaultdict(lambda: 0)

    def init(self) -> None:
        """Method to configure client connection.

        Must be called before any other methods are used.
        """

        pass

    def new(self, state=None) -> int:
        """Method to get a new state from server.

        Args:
            state (List): if None, state will be in default state. Otherwise, must match formalism of server.

        Returns:
            int: key for the new state generated.
        """

        if state is None:
            args = []
        else:
            args = [state]

        return self._send_message(QuantumManagerMsgType.NEW, args)

    def get(self, key: int) -> any:
        return self._send_message(QuantumManagerMsgType.GET, [key])

    def run_circuit(self, circuit: "Circuit", keys: List[int]) -> any:
        return self._send_message(QuantumManagerMsgType.RUN, [circuit, keys])

    def set(self, keys: List[int], amplitudes: any) -> None:
        self._send_message(QuantumManagerMsgType.SET, [keys, amplitudes])

    def remove(self, key: int) -> None:
        self._send_message(QuantumManagerMsgType.REMOVE, [key])

    def kill(self) -> None:
        """Method to terminate the connected server.

        Side Effects:
            Will end all processes of remote server.
            Will set the `connected` attribute to False.
        """
        self._send_message(QuantumManagerMsgType.TERMINATE, [], expecting_receive=False)

    def _send_message(self, msg_type, args: List, expecting_receive=True) -> any:
        self.type_counter[msg_type.name] += 1
        tick = time()

        msg = QuantumManagerMessage(msg_type, args)
        data = dumps(msg)
        self.s.sendall(data)

        if expecting_receive:
            received_data = self.s.recv(1024)
            received_msg = loads(received_data)
            self.io_time[msg_type.name] += time() - tick
            return received_msg

        self.io_time[msg_type.name] += time() - tick


if __name__ == '__main__':
    parser = generate_arg_parser()
    args = parser.parse_args()

    client = QuantumManagerClient(args.ip, args.port)
    client.init()

    # send request for new state
    key = client.new()

    # send request to get state
    ket_vec = client.get(key)
    print("|0> state:", ket_vec.state)

    # run Hadamard gate
    circ = Circuit(1)
    circ.h(0)
    client.run_circuit(circ, [key])

    ket_vec = client.get(key)
    print("|+> state:", ket_vec.state)

