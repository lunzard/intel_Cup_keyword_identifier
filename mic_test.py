import numpy as np
import sounddevice as sd
import time
import librosa
from collections import deque
import threading

from keras.models import load_model

model = load_model('mfcc.h5')

sample_rate = 16000
sample_queue = deque([], maxlen=12000)

state_dict = {
    0: 'Background',
    1: 'Clap',
    2: "Deng",
    3: "Di Qiu",
    4: "Grah",
    5: "Hello",
    6: "Kai",
    7: "Lights",
    8: "Music",
    9: "On",
    10: "Planet",
    11: "Time",
    12: "What",
    14: "Unknown"
}


class AudioHandler:
    def __init__(self, sr, queue):
        self.sr = sr
        self.stream = sd.InputStream(samplerate=self.sr,
                                     channels=1,
                                     callback=self.callback,
                                     blocksize=int(self.sr / 5))
        self.mic_queue = queue
        # self.mic_queue.extend(np.zeros((self.sr, 1)))

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.close()

    def run_set_time(self, seconds):
        time.sleep(seconds)

    def callback(self, in_data, frame_count, time_info, flag):
        self.mic_queue.extend(in_data.tolist())
        print(flag)


def mic_data():
    audio = AudioHandler(sample_rate, sample_queue)
    audio.start()
    audio.run_set_time(100.0)
    # audio.stop()


def state_predict():
    while True:
        # ps = np.array(sample_queue).reshape(22050,)
        # print(any(np.isnan(ps)))
        # sd.play(np.array(sample_queue).reshape(22050, ), sample_rate)
        ps = librosa.effects.preemphasis(np.array(sample_queue).reshape(12000, ))

        # ps = librosa.feature.melspectrogram(y=ps, sr=sample_rate, n_mels=64,
        #                                     fmin=0, fmax=8000)
        # ps = librosa.amplitude_to_db(ps, ref=np.min)
        ps = librosa.feature.mfcc(y=ps, sr=sample_rate)
        q = model.predict(np.array([ps.reshape((20, 24, 1))]))
        # print(state_dict.get(int(np.argmax(q)), "NOT RECOGNIZED"))

        b = np.argsort(q[0], axis=0)
        if b[len(b) - 1]!= 0:
            print(state_dict.get(b[len(b) - 1], "NOT RECOGNIZED"), state_dict.get(b[len(b) - 2], "NOT RECOGNIZED"))
        time.sleep(0.1)


if __name__ == "__main__":
    # 0 idle, 1 Grenade   2 Shield    3 Reload     4 Logout
    x = threading.Thread(target=mic_data)
    y = threading.Thread(target=state_predict)
    print("data start")
    x.start()
    time.sleep(3)
    print("predict start")

    y.start()

    x.join()
    y.join()
