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

ACTION_COMMAND_ADDR = 'action_command_list.txt'
ACTIVATE_COMMAND_ADDR = 'activate_command_list.txt'



class Recorder:
    def __init__(self):
        self.repeaters = {}
        self.repeat_limit = 2 # consecutive word limit
    def add_words(self, words):
        new_repeaters = {}
        priority = self.repeat_limit
        for word in words:
            has_repeater = False
            for repeater in self.repeaters.keys():
                if word == repeater:
                    new_repeaters[repeater] = [self.repeaters[repeater][0] + 1, self.repeaters[repeater][1]]
                    new_repeaters[repeater][1] += priority
                    has_repeater = True
                    break
            if not has_repeater:
                new_repeaters[word] = [1, priority]
            priority -= 1
        self.repeaters = new_repeaters
    def create_words(self,words):
        priority = self.repeat_limit
        for word in words:
            self.repeaters[word] = [1, priority]
            priority -=1
    def check_keyword(self):
        remain_repeaters = {}
        keywords =[]
        for repeater in self.repeaters.keys():
            repeat_time = self.repeaters[repeater][0]
            priority = self.repeaters[repeater][1]
            # if repeat more than 3 times
            if repeat_time >= self.repeat_limit and priority >= repeat_time:
                keywords.append(repeater)
            else:
                remain_repeaters[repeater] = [repeat_time, priority]
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
    if words[0].lower() == "background":
        return None
    if recorder.repeaters:
        recorder.add_words(words)
        return recorder.check_keyword()
    else: 
        recorder.create_words(words)
        return None

def check_sentence(sentence, commands, new_word):
    remaining_choices = []
    for i in sentence.choices:
        if new_word == (commands[i])[sentence.last_pos + 1]:
            remaining_choices.append(i)
    # print('remain_choices is ', remaining_choices)
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
                # print('check choices: ', j.choices)               
                # do forward checking
                remaining_choices = check_sentence(j, commands, i)
                # print('there is remmaining choices of ',i, ' --> ', remaining_choices )
                if remaining_choices:
                    new_sentence = Sentence(j.priority,j.last_word, (j.choices).copy(), j.last_pos)
                    new_sentence.extend(i, rank, remaining_choices.copy())
                    new_sentences.append(copy.deepcopy(new_sentence))
                    rank += 1

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

def show_sentence_progress(top_n_sentences, commands):
    first_sentence = top_n_sentences[0]
    first_choice_index = first_sentence.choices[0]
    command_1 = commands[first_choice_index]
    command_content = command_1[:first_sentence.last_pos + 1]
    progress_string = ""
    for word in command_content:
        progress_string += word
        progress_string += " "
    return progress_string





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
def convert_predictions(queue_predictions, queue_commands, action_commands, activate_commands):
    # a flag that shows the start of prediction
    is_predict_start = False
    # a flag that switch between activate_commands and action_commands
    is_activate = False
    # a list of objects that keep track of possible predictions
    sentences = []
    recorder = Recorder()
    # 1.5 seconds time limit to skip some words eg.'the' in the commands
    time_lost_limit = 1.5
    # 10 seconds time limit to stop action detection and switch back to activate detection
    time_restart_limit = 5

    is_prediction_lost = False

    connected = True
    while connected:
        if not queue_predictions.empty():
            prediction_msg = queue_predictions.get()
            if prediction_msg == DISCONNECT_MESSAGE:
                connected = False
            else:
                words = get_predictions(recorder,prediction_msg)
                if words:
                    # after activation voice is detected
                    if is_activate:
                        print('get action word:', words)
                        is_predict_start, top_n_sentences = searcher(is_predict_start,
                        words, sentences, action_commands)
                        # print('remaining choices: ', top_n_sentences[0].choices)
                        if is_predict_start:
                            if top_n_sentences:
                                sentences = top_n_sentences
                                # possible_commands = show_possible_choices(top_n_sentences)
                                possible_commands = show_sentence_progress(top_n_sentences, action_commands)
                                # send commands indices to flutter
                                queue_commands.put(possible_commands)
                                is_prediction_lost = False
                            elif not is_prediction_lost:
                                time_lost_start = time.time()
                                is_prediction_lost = True
                            else:
                                time_lost = time.time() - time_lost_start
                                if time_lost >= time_restart_limit:
                                    is_activate = False
                                    is_predict_start = False
                                    is_prediction_lost = False
                                    sentences = []
                                elif time_lost >= time_lost_limit:
                                    is_predict_start = False
                                    is_prediction_lost = False
                                    sentences = []
                                    queue_commands.put('$_timeout_$')
                        else:
                            sentences = []
                            # reach the end
                            if top_n_sentences:
                                # only_index = top_n_sentences[0].choices[0]
                                # send the first index to flutter
                                # queue_commands.put(str(only_index))
                                possible_commands = show_sentence_progress(top_n_sentences, action_commands)
                                # send commands indices to flutter
                                queue_commands.put(possible_commands + '_#')

                                is_activate = False

                                # empty the inferences for 2 seconds
                                # queue_commands.put('$_' + 'okay' + '_$')
                                is_clear = False
                                time_clear_start = time.time()
                                while not is_clear:
                                    time_clear_now = time.time()
                                    if time_clear_now - time_clear_start >= 2:
                                        is_clear = True
                                    queue_predictions.get()
                                    # time.sleep(0.5)
                    
                    # before activation voice is detected
                    else:
                        print('get activate word:', words)
                        is_predict_start, top_n_sentences = searcher(is_predict_start,
                        words, sentences, activate_commands)
                        # print('remaining choices: ', top_n_sentences[0].choices)
                        if is_predict_start:
                            if top_n_sentences:
                                sentences = top_n_sentences
                                # '#_' is to differentiate action and activate commands for flutter app
                                # possible_commands = '#_' + show_possible_choices(top_n_sentences)
                                possible_commands = '#_' + show_sentence_progress(top_n_sentences, activate_commands)
                                # send commands indices to flutter
                                queue_commands.put(possible_commands)
                                is_prediction_lost = False
                            elif not is_prediction_lost:
                                time_lost_start = time.time()
                                is_prediction_lost = True
                            else:
                                time_lost = time.time() - time_lost_start
                                if time_lost >= time_lost_limit:
                                    is_predict_start = False
                                    is_prediction_lost = False
                                    sentences = []
                                    queue_commands.put('$_timeout_$')
                        else:
                            sentences = []
                            # reach the end
                            if top_n_sentences:
                                # only_index = top_n_sentences[0].choices[0]
                                # send the first index to flutter
                                # queue_commands.put('#_' + str(only_index))
                                possible_commands = show_sentence_progress(top_n_sentences, activate_commands)
                                # send commands indices to flutter
                                queue_commands.put('#_'+ possible_commands + '_#')
                                is_activate =True
                                # empty the inferences for 1.5 seconds
                                # queue_commands.put('$_' + 'Hi what can I help you' + '_$')
                                is_clear = False
                                time_clear_start = time.time()
                                while not is_clear:
                                    time_clear_now = time.time()
                                    if time_clear_now - time_clear_start >= 2:
                                        is_clear = True
                                    queue_predictions.get()
                                    # time.sleep(0.5)

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
    action_commands =scan_commands(ACTION_COMMAND_ADDR)
    activate_commands =scan_commands(ACTIVATE_COMMAND_ADDR)
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
    p_convert = multiprocessing.Process(target=convert_predictions, args=(queue_predictions, queue_commands, action_commands, activate_commands))
    p_send.start()
    p_convert.start()

    is_alive = True
    while is_alive:
        # user_command = input("send <logout> if you want to quit the program")
        user_command = ''
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

