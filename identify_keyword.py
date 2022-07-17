import time
import socket
import multiprocessing
import os.path
import copy

# define the length of header
HEADER = 1024
# recieving port of current script
PORT_IN = 5151
# destintion port of flutter UI
PORT_OUT = 5454
SERVER = 'localhost'
# combine server and port into a tuple 
ADDR1 = (SERVER, PORT_IN)
ADDR2 = (SERVER, PORT_OUT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"

FILE_ADDR = 'command_list.txt'



class Recorder:
    def __init__(self):
        self.repeaters = {}
        self.repeat_limit = 3 # consecutive word limit
    def add_words(self, words):
        new_repeaters = {}
        for word in words:
            has_repeater = False
            for repeater in self.repeaters.keys():
                if word == repeater:
                    new_repeaters[repeater] = self.repeaters[repeater] + 1
                    has_repeater = True
                    break
            if not has_repeater:
                new_repeaters[word] = 1
        self.repeaters = new_repeaters
    def create_words(self,words):
        for word in words:
            self.repeaters[word] = 1
    def check_keyword(self):
        remain_repeaters = {}
        keywords =[]
        for repeater in self.repeaters.keys():
            repeat_time = self.repeaters[repeater]
            # if repeat more than 3 times
            if repeat_time >= self.repeat_limit:
                keywords.append(repeater)
            else:
                remain_repeaters[repeater] = repeat_time
        self.repeaters = remain_repeaters
        return keywords

class Sentence:
    def __init__(self, rank, new_word, choices, position):
        self.priority = rank
        self.last_word = new_word
        self.choices = choices # indices of current commands list
        self.last_pos = position
    def extend(self, new_word, rank, choices):
        self.priority += rank
        self.last_word = new_word
        self.last_pos += 1
        self.choices = choices

def scan_commands(file_address):
    commands = []
    if os.path.exists(file_address):
        f = open(file_address, "r")
        end_of_file =False
        while not end_of_file:
            command_string = f.readline()
            if command_string:
                command = command_string.split(' ')
                command = [x.strip() for x in command_string.split(' ')]
                commands.append(command.copy())
            else:
                end_of_file = True
        f.close()
    return commands




def get_predictions(recorder, inputs):
    words = inputs.split(' ')
    if recorder.repeaters:
        recorder.add_words(words)
        return recorder.check_keyword()
    else: 
        recorder.create_words(words)
        return None

def check_sentence(sentence, commands, new_word):
    remaining_choices = []
    for i in sentence.choices:
        print(new_word, (commands[i])[sentence.last_pos + 1])
        if new_word == (commands[i])[sentence.last_pos + 1]:
            remaining_choices.append(i)
            print('is the same!')
    print('remain_choices is ', remaining_choices)
    return remaining_choices

def compare_sentence(sentence):
    return sentence.priority


# method that called repeatedly
# when new group of possible predictons arrive
# predictions: a dict of 'word - priority'
def searcher(is_predict_start, new_predictions, sentences, commands):
    new_sentences = []
    if is_predict_start:
        for j in sentences:
            rank = 1
            for i in new_predictions:
                print('check choices: ', j.choices)               
                # do forward checking
                remaining_choices = check_sentence(j, commands, i)
                if remaining_choices :
                    print('there is remmaining choices of ',i, ' --> ', remaining_choices )
                    new_sentence = Sentence(j.priority,j.last_word, (j.choices).copy(), j.last_pos)
                    new_sentence.extend(i, rank, remaining_choices.copy())
                    new_sentences.append(copy.deepcopy(new_sentence))
                    rank += 1
                else:
                    print('remaining_choices become empty!: ',  i)
    else:
        is_predict_start = True
        rank = 1
        for i in new_predictions:
            inital_sentence = Sentence(rank, i, [], 0)
            for k in range(len(commands)):
                if i == (commands[k])[0]:
                    (inital_sentence.choices).append(k)
            if inital_sentence.choices:
                new_sentences.append(inital_sentence)
                rank += 1
        if not new_sentences:
            is_predict_start = False
    if new_sentences:         
        new_sentences.sort(key= compare_sentence, reverse=False)
        is_all_end = True
        for new_sentence in new_sentences:
            if new_sentence.last_pos + 1 != len(commands[new_sentence.choices[0]]):
                is_all_end = False
                break
        if is_all_end:
            is_predict_start = False

    return is_predict_start, new_sentences

def show_possible_choices(top_n_sentences):
    choices_string = ""
    for sentence in top_n_sentences:
        for choice in sentence.choices:
            choices_string += str(choice)
            choices_string += " "
    return choices_string


# communication with ai_prediction script
# a Process that runs in a loop
def receive_predictions(queue_predictions, src_server):
    conn, addr = src_server.accept()
    connected = True
    while connected:
        try:
            msg =conn.recv(HEADER).decode(FORMAT)
            if msg == DISCONNECT_MESSAGE:
                connected = False
            queue_predictions.put(msg)
        except:
            time.sleep(0.2)
    conn.close()

# a Process that convert predictions into possible command indices
def convert_predictions(queue_predictions, queue_commands, commands):
    # a flag that shows the start of prediction
    is_predict_start = False
    # a list of objects that keep track of possible predictions
    sentences = []
    recorder = Recorder()
    # 2 seconds time limit to skip some words eg.'the' in the commands
    time_lost_limit = 2 
    is_predictoin_lost = False

    connected = True
    while connected:
        if not queue_predictions.empty():
            prediction_msg = queue_predictions.get()
            if prediction_msg == DISCONNECT_MESSAGE:
                connected = False
            else:
                words = get_predictions(recorder,prediction_msg)
                if words:
                    print('get predictions:', words)
                    is_predict_start, top_n_sentences = searcher(is_predict_start,
                     words, sentences, commands)
                    # print('remaining choices: ', top_n_sentences[0].choices)
                    if is_predict_start:
                        if top_n_sentences:
                            sentences = top_n_sentences
                            possible_commands = show_possible_choices(top_n_sentences)
                            # send commands indices to flutter
                            queue_commands.put(possible_commands)
                            is_predictoin_lost = False
                        elif not is_predictoin_lost:
                            time_lost_start = time.time()
                            is_predictoin_lost = True
                        else:
                            time_lost = time.time() - time_lost_start
                            if time_lost >= time_lost_limit:
                                is_predict_start = False
                    else:
                        sentences = []
                        if top_n_sentences:
                            only_index = top_n_sentences[0].choices[0]
                            # send the first index to flutter
                            queue_commands.put(str(only_index))


        else:
            time.sleep(0.2)

# a Process that send command_indices to flutter app
def send_commands(queue_commands, dest_server):
    connected = True
    while connected:
        if not queue_commands.empty():
            msg = queue_commands.get()
            if msg == DISCONNECT_MESSAGE:
                connected = False
            else:
                message =msg.encode(FORMAT)
                dest_server.send(message)
        else:
            time.sleep(0.2)

if __name__ == '__main__':
    print('is the main running')
    commands =scan_commands(FILE_ADDR)
    queue_predictions = multiprocessing.Queue()
    queue_commands = multiprocessing.Queue()
    src_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dest_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        src_server.bind(ADDR1)
    except:
        print('error in binding address1, pls logout')
    else:
        print('addr1 combined successfully!')
        src_server.listen()
        p_recv = multiprocessing.Process(target=receive_predictions, args=(queue_predictions, src_server))
        p_recv.start()
    dest_server.connect(ADDR2)

    
    p_send = multiprocessing.Process(target=send_commands, args=(queue_commands, dest_server))
    p_convert = multiprocessing.Process(target=convert_predictions, args=(queue_predictions, queue_commands, commands))
    p_send.start()
    p_convert.start()

    is_alive = True
    while is_alive:
        user_command = input("send <logout> if you want to quit the program")
        if user_command == 'logout':
            print('now closing identify_keyword.py ...')
            # time.sleep(5)
            is_alive = False
    queue_predictions.put(DISCONNECT_MESSAGE)
    queue_commands.put(DISCONNECT_MESSAGE)
    time.sleep(2)
    p_recv.terminate()
    p_send.terminate()
    p_convert.terminate()
    src_server.close()
    dest_server.close()
    print('all process and sockets are closed, bye!')

