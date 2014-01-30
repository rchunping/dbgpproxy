__author__ = 'grkr'

import asyncore
import socket
import getopt
from xml.dom import minidom


E_NO_ERROR = 0
E_PARSE_ERROR = 1
E_INVALID_OPTIONS = 3
E_UNIMPLEMENTED_COMMAND = 4


class RegistrationHandler(asyncore.dispatcher_with_send):
    def __init__(self, manager, sock=None, map=None):
        super().__init__(sock, map)

        self._manager = manager

    def send(self, data):
        l = len(data)
        data = '{0:d}\0{1:s}\0'.format(l, data)

        super().send(data.encode())

    def _parse_line(self, line):
        """

        @type line: string
        """
        line = line.strip().rstrip('\0')
        if not line:
            return None, None, line

        command, args = line.split(' ', maxsplit=1)

        return command, args.split(), line

    def handle_read(self):
        data = self.recv(1024)
        if data:
            command, args, line = self._parse_line(data.decode())

            if not command:
                self._error('proxyerror', 'Failed to parse command.', E_PARSE_ERROR)

            print('command = %s, args = %s' % (command, args))
            if command == 'proxyinit':
                self._handle_proxyinit(args)
            elif command == 'proxystop':
                self._handle_proxystop(args)
            else:
                self._error('proxyerror', 'Unknown command [{0:s}]'.format(command), E_UNIMPLEMENTED_COMMAND)

    def _handle_proxyinit(self, args):
        print('got proxyinit command: %s' % (args,))

        idekey = port = multi = None
        opts, args = getopt.getopt(args, 'p:k:m:')

        for o, a in opts:
            if o == '-p':
                port = int(a)
            elif o == '-k':
                idekey = a
            elif o == '-m':
                multi = a

        if not idekey:
            self._error('proxyinit', 'No IDE key defined for proxy.', E_INVALID_OPTIONS)
            return

        if not port:
            self._error('proxyinit', 'No port defined for proxy.', E_INVALID_OPTIONS)
            return

        id = self._manager.add_server(idekey, self.addr[0], port, multi)
        if id:
            msg = u'<?xml version="1.0" encoding="UTF-8"?>\n<proxyinit success="1" idekey="{0:s}" address="{1:s}" port="{2:d}"/>'.format(
                id, 'localhost', 9000)
            self.send(msg)
            return
        else:
            self._error('proxyinit', 'IDE Key already exists.', E_INVALID_OPTIONS)
            return

    def _handle_proxystop(self, args):
        print('got proxystop command: %s' % (args))

        opts, args = getopt.getopt(args, 'k:')
        idekey = None
        for o, a in opts:
            if o == '-k':
                idekey = a

        if not idekey:
            self._error('proxystop', 'No IDE key.', E_INVALID_OPTIONS)
            return

        id = self._manager.remove_server(idekey)
        msg = u'<?xml version="1.0" encoding="UTF-8"?>\n<proxystop success="1" idekey="{0:s}"/>'.format(id)
        self.send(msg)
        return

    def _error(self, command, message, code=E_NO_ERROR):
        error = u'<?xml version="1.0" encoding="UTF-8"?>\n<{0:s} success="0"><error id="{1:d}"><message>{2:s}</message></error></{0:s}>'.format(
            command, code, message)

        self.send(error)
        self.close()


class RegistrationServer(asyncore.dispatcher):
    def __init__(self, host, port, manager):
        asyncore.dispatcher.__init__(self)
        self._port = port
        self._host = host

        self._manager = manager

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))

        print('listening for registration requests on {}:{}...'.format(host, port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print('incoming registration connection from {}'.format(repr(addr)))
            handler = RegistrationHandler(self._manager, sock=sock)


class ToIDEHandler(asyncore.dispatcher_with_send):
    def __init__(self, sock, debug_sock):
        super().__init__(sock)
        self._debug_sock = debug_sock

    def handle_read(self):
        #print('ToIDEHandler: handle_read()')
        data = self.recv(1024)
        if data:
            print('<-- {}'.format(data.decode()))
            self._debug_sock.send(data)

    def handle_close(self):
        self.close()


class DebugConnectionHandler(asyncore.dispatcher_with_send):
    def __init__(self, manager, sock=None, map=None):
        super().__init__(sock, map)

        self._manager = manager
        self._initialized = False
        self._ide_socket = None
        self._ide_handler = None

    def handle_read(self):
        #print('DebugConnectionHandler: handle_read()')

        # initialize the debugger session
        if not self._initialized:
            self._handle_init_packet()
            return

        # now play man in the middle ;)
        data = self.recv(1024)
        if data:
            print('--> {}'.format(data.decode()))
            self._ide_handler.send(data)


    def _handle_init_packet(self):
        data = self.recv(100)

        # look for first NUL byte
        eol = data.find(b'\x00')

        # extract message length
        try:
            msg_len = int(data[:eol])
            print('msg_len = {}'.format(msg_len))
        except ValueError:
            print('invalid protocol')
            # TODO send error to debugging engine
            self.close()
            return

        # skip \x00
        data = data[eol+1:]

        # calculate remaining data length
        remaining_size = msg_len - len(data) + 1

        # get remaining data for init packet
        while remaining_size > 0:
            print("getting more data size={}", remaining_size)
            new_data = self.recv(remaining_size)
            data = data + new_data
            remaining_size -= len(new_data)

        # skip \x00
        data = data[:msg_len]

        dom = minidom.parseString(data.decode())
        init_packet = dom.documentElement
        packet_type = init_packet.localName

        if packet_type != 'init':
            print('expected init packet, got {}'.format(packet_type))
            # TODO send error to debugging engine
            self.close()
            return

        # get/set information from/in init packet
        idekey = init_packet.getAttribute('idekey')
        server = self._manager.get_server(idekey)
        if not server:
            print('no server with IDE key [{}], aborting'.format(idekey))
            # TODO send error
            self.close()
            return

        # TODO should set proxied = DEBUGGER IP ADDR
        init_packet.setAttribute('proxied', '127.0.0.1')

        # TODO connect to server (i.e. IDE)
        if not self.connect_to_server(server, init_packet):
            print('unable to connect to server with IDE key [{}], aborting and removing server'.format(idekey))
            # TODO send error (proxyerror)
            self._manager.remove_server(idekey)
            self.close()
            return


        self._initialized = True

    def connect_to_server(self, server, init_packet):
        server_addr = server[0]

        try:
            print('trying to connect to {}:{}'.format(server_addr[0], server_addr[1]))
            self._ide_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._ide_socket.connect((server_addr[0], server_addr[1]))
            print('connected')
        except socket.error:
            print('unable to connect to {}:{}'.format(server_addr[0], server_addr[1]))
            return False

        if not init_packet.hasAttribute('hostname') or not init_packet.getAttribute('hostname'):
            # FIXME set client hostname
            init_packet.setAttribute('hostname', '127.0.0.1')

        # send the init packet to the server (IDE)
        response = u'<?xml version="1.0" encoding="UTF-8"?>\n'
        response += init_packet.toxml()
        l = len(response)
        print('sending init to IDE {0:d}\0{1:s}\0'.format(l, response))
        self._ide_socket.send('{0:d}\0{1:s}\0'.format(l, response).encode())
        self._ide_handler = ToIDEHandler(self._ide_socket, self)

        return True

    def handle_close(self):
        if self._ide_handler is not None:
            print('closing IDE socket')
            self._ide_handler.close()
        self.close()


class DebugConnectionServer(asyncore.dispatcher):
    def __init__(self, host, port, manager):
        asyncore.dispatcher.__init__(self)

        self._host = host
        self._port = port
        self._manager = manager

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host, port))

        print('listening for debugger connections on {}:{}'.format(host, port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            print('incoming debugger connection from {}'.format(repr(addr)))
            handler = DebugConnectionHandler(self._manager, sock=sock)


class Proxy:
    def __init__(self):
        self._servers = {}

        self._registration_server = RegistrationServer('localhost', 9001, manager=self)
        self._debugger_connection_server = DebugConnectionServer('localhost', 9000, manager=self)

    def start(self):
        asyncore.loop()

    def add_server(self, idekey, host, port, multi):
        if idekey in self._servers:
            return None

        self._servers[idekey] = [[host, port], multi]
        print('add_server: idekey = {}, host = {}, port = {}, multi = {}'.format(idekey, host, port, multi))
        return idekey

    def remove_server(self, idekey):
        if idekey in self._servers:
            print('remove_server: idekey = {}'.format(idekey))
            del self._servers[idekey]
            return idekey

        return None

    def get_server(self, idekey):
        if idekey in self._servers:
            return self._servers[idekey]

        return None


if __name__ == "__main__":
    Proxy().start()