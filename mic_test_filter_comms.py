import numpy as np
import sounddevice as sd
import time
import librosa
from collections import deque
import threading

from keras.models import load_model

import socket

################ comms ##################
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
###############comms end ####################

model = load_model("../scripts/16kv_2.h5")

sample_rate = 16000
sample_queue = deque([], maxlen=12000)
sample_queue.extend(np.zeros((sample_rate, 1)))

state_dict = dict()

with open('../scripts/keywords.txt') as f:
    keywords_list = f.read().splitlines()
    no_of_keywords = len(keywords_list)

    for id, keyword in enumerate(keywords_list):
        state_dict[id] = keyword
    state_dict[no_of_keywords] = 'unknown'

def callback(in_data, frame_count, time_info, flag):
    sample_queue.extend(in_data.tolist())
    # print(flag)

if __name__ == "__main__":
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.connect(ADDR)

    print("data start")
    try:
        with sd.InputStream(samplerate=sample_rate,
                            channels=1,
                            callback=callback,
                            blocksize=int(sample_rate / 10)):
            print("predict start")
            while True:
                ps = librosa.effects.preemphasis(np.array(sample_queue).reshape(12000, ))
                ps = librosa.feature.mfcc(y=ps, sr=sample_rate)
                q = model.predict(np.array([ps.reshape((20, 24, 1))]))

                b = np.argsort(q[0], axis=0)
                if b[len(b) - 1] != 0:
                    # print(state_dict.get(b[len(b) - 1], "NOT RECOGNIZED"), state_dict.get(b[len(b) - 2], "NOT RECOGNIZED"))
                    predict1 = state_dict.get(b[len(b) - 1], "NOT RECOGNIZED")
                    predict2 = state_dict.get(b[len(b) - 2], "NOT RECOGNIZED")
                    print(predict1, predict2)
                    msg = predict1 + ' ' + predict2
                    send(server, msg)
                else:
                    print()
                time.sleep(0.1)
    except KeyboardInterrupt:
        print('Interrupted by user')
    except Exception as e:
        print(type(e).__name__ + ': ' + str(e))

    server.close()
