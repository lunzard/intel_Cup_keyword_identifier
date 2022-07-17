import socket

HEADER = 1024
PORT = 5151
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"
SERVER = 'localhost'
ADDR = (SERVER, PORT)

def send(server, msg):
    message = msg.encode(FORMAT)
    server.send(message)
    print("msg sent: ", message.decode(FORMAT))



server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.connect(ADDR)

connected = True

while connected:
    msg = input('Enter message to identify_keyword.py: ')
    if msg == 'exit':
        connected = False
        server.close()
    else:
        send(server, msg)