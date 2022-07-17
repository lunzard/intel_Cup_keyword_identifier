import socket

from matplotlib.pyplot import connect

HEADER = 1024
PORT = 5454
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"
SERVER = 'localhost'
ADDR = (SERVER, PORT)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

def recieve(conn):
    connected =True
    while connected:
        msg = conn.recv(HEADER).decode(FORMAT)
        print("recieve: " , msg)
        if msg == DISCONNECT_MESSAGE:
            conn.close()
            connected = False


server.listen()
print(f"[LISTENING] Server is listening on {SERVER}")
connected = True
conn, addr = server.accept()
recieve(conn)

server.close()