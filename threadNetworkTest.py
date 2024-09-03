import socket
import threading
import time
import hashlib

PORT = 5060
READ_SIZE = 2048

def listen(responses, run):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    sock.bind(("", PORT))

    print("UDP server listening...\n")

    while(run[0]):
        try:
            data, (address, port) = sock.recvfrom(READ_SIZE)
            print(data.decode("utf-8"))
            responses.append(data.decode("utf-8"))
        except socket.timeout:
            continue




def run():
    responses = []
    run = [True]
    listenerThread = threading.Thread(target=listen, args=(responses, run))
    listenerThread.daemon = True
    listenerThread.start()

    test = ""
    while test != "exit":
        test = input("Enter an input")

    run[0] = False
    print("Ending listener thread")
    print(run)
    listenerThread.join()

    print("Number of responses: {}".format(len(responses)))

run()

