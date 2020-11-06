import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

import numpy as np
from gensim.models import word2vec

from sklearn.svm import SVC

from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException
from beem.vote import AccountVotes

from datetime import datetime, timedelta
import time
from threading import Thread
import random

from inspect import getsourcefile
import os
import os.path as path, sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])

# Module from parent Directory
import config  
import database, helper

sys.path.pop(0)

device = T.device("cuda" if T.cuda.is_available() else "cpu")
print("Device available for running: " + device.type)

class TextCNN(nn.Module):
    def __init__(self):
        super(TextCNN, self).__init__()

        self.convs = nn.ModuleList([
                    nn.Conv2d(1, config.KERNEL_NUM, (i, config.EMBEDDING_DIM)) for i in config.WINDOW_SIZES ])

        self.dropout = nn.Dropout(0.15)
        self.fc1 = nn.Linear(config.KERNEL_NUM * len(config.WINDOW_SIZES), config.KERNEL_NUM * len(config.WINDOW_SIZES))
        self.fc2 = nn.Linear(config.KERNEL_NUM * len(config.WINDOW_SIZES), len(config.CATEGORIES))

    def forward(self, x):
        # CONVS
        xs = []
        for conv in self.convs:
            x2 = T.tanh(conv(x.unsqueeze(1)))
            x2 = T.squeeze(x2, -1)
            x2 = F.max_pool1d(x2, x2.size(2))
            x2 = self.dropout(x2)
            xs.append(x2)
        x = T.cat(xs, 2)

        # FC
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        
        x = self.fc2(x)
        x = F.softmax(x, dim = 1)

        return x

    @staticmethod
    def load_model(path):
        model = TextCNN()
        if os.path.exists(path):
            model.load_state_dict(T.load(path))
            print("Loaded existent TextCNN")

        return model.to(device)

    @staticmethod
    def save_model(model, path):
        model.to('cpu')
        T.save(model.state_dict(), path)
        model.to(device)


class WordEmbedding():
    @staticmethod
    def vectorize_text(model : word2vec.Word2Vec, html = None, text = None):
        if html is not None:
            # Html to text and add to text
            if text is None:
                text = ''
            text += helper.html_to_text(html)

        if text is not None:
            text = helper.pre_process_text(text)

            # Create wordmap
            text = text.replace('.', ' ')
            words = list(filter(lambda x: x in model.wv.vocab, text.split()))
            
            #vectorize
            if len(words) >= 20:
                return T.Tensor([[model.wv.word_vec(w) for w in words]]).to(device)
        
        
        return None


class Profiler():
    def __init__(self, username : str, start_get_post_thread=True):
        self.username = username
        self.account = Account(username, blockchain_instance=Hive())

        mysql_con = config.get_connection()
        if mysql_con is None:
            print("[INFO] Can't start Latest Post Manager because of an mysql database error!")
            return
               
        result = database.read_query("SELECT * FROM profiler WHERE username=%s;", (username, ), con=mysql_con, close_con=False)
        if len(result) == 0:
            # No profiler exists, create one
            self.category = [0 for i in config.CATEGORIES]
            self.data_length = 0
            result = database.commit_query("INSERT INTO profiler(username, category, length, timestamp) VALUES (%s, %s, %s, %s);",
                                         (username, ' '.join(map(str, self.category)), self.data_length, datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S")),con=mysql_con, close_con=False)
            if result <= 0:
                # Error
                print("[WARNING] Can't add Profiler for " + username)
            else:
                # Start analyze Thread, if the profiler existed bevor, this thread already run!
                self.analyze_thread = Thread(target=self.analyze_activity)
                self.analyze_thread.name = "Analyze Activities from " + username
                self.analyze_thread.daemon = True
                self.analyze_thread.start()
        else:
            # Load existent Profiler
            self.update_timestamp()

            self.category = [float(x) for x in result[0][1].split(' ')]
            self.data_length = result[0][2]    

        mysql_con.close()
        # Start finder thread
        self.find_posts_thread = Thread(target=self.find_interestings)
        self.find_posts_thread.name = "Find interesting Posts for " + username
        self.find_posts_thread.daemon = True
        if start_get_post_thread:
            self.find_posts_thread.start()          

    def update_timestamp(self):
        # Update timestamp in database --> No kickoff
        query = "UPDATE profiler SET timestamp=%s WHERE username=%s;"
        result = database.commit_query(query, (datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), self.username))
        
    def update(self):
        # Update category, data_length, timestamp in database
        query = "UPDATE profiler SET category=%s, length=%s, timestamp=%s WHERE username=%s;"
        str_arr = ' '.join(map(str, self.category))
        result = database.commit_query(query, (str_arr, self.data_length, datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), self.username))

    def add_categories(self, _output, factor):
        l = _output.data[0].tolist()
        self.data_length += 1

        if self.data_length == 1:
            # First data --> Next one
            self.category = l
            return

        # Get 5 highest categories
        top_cats = []       
        cat = l.copy()      
        while len(top_cats) < 5:
            highest = (0, -1) # (value, cat_index)
            for index, x in enumerate(cat):
                if highest[1] == -1 or x > highest[0]:
                    # first or better
                    highest = (x, index)

            top_cats.append(highest)
            cat[highest[1]] = 0

        # Only calc averages for the 5 main categories
        for value, index in top_cats:
            self.category[index] = (self.category[index] + value * factor) / (1 + factor)

        self.update()
        return

        if self.data_length == 0:
            # First data
            self.category = l
        else:
            # Calc average
            self.category = [((self.category[i] + l[i] * factor) / (1 + factor)) for i in range(len(self.category))]

        self.data_length += 1
        self.update()

    def analyze_activity(self):
        # Posts
        for comment in self.account.history_reverse(only_ops=['comment']):
            if comment['author'] != self.username:
                # Activity, he does not (Someone else commented at his blog...)
                continue

            _input = WordEmbedding.vectorize_text(model=config.statics.Word2Vec, html=comment['body'], text=comment['title'] + ". ")
            if _input is None:
                # To less words or Error
                continue

            _output = config.statics.TextCNN(_input).cpu()
            self.add_categories(_output, factor=2) # Posts count double
            time.sleep(0.5)

            if self.data_length >= config.PROFILER_MIN_DATA:
                # make brake
                time.sleep(0.75)
            if self.data_length >= config.PROFILER_MAX_DATA:
                break

        # Votes
        return
        for vote in self.account.history_reverse(only_ops=['vote']):
            if vote['voter'] == self.username and vote['voter'] != vote['author']:
                # If I am the voter and it is not my post
                c = Comment(f"@{vote['author']}/{vote['permlink']}", blockchain_instance=Hive())
                
                # vectorize
                _input = WordEmbedding.vectorize_text(model=config.statics.Word2Vec, html=c.body, text=c.title + ". ")
                if _input is None:
                    continue

                _output = config.statics.TextCNN(_input).cpu()
                self.add_categories(_output, factor=1)

                # wait for next request --> Prevent overflow
                time.sleep(0.9)
            
            if self.data_length >= config.PROFILER_MAX_DATA:
                break

    def find_interestings(self):
        while self.data_length < config.PROFILER_MIN_DATA:
            # Wait until enough data is availabel
            time.sleep(0.2)

        mysql_con = config.get_connection()
        while 1:
            # 0 Step: Check if post limit is reached
            interesting_posts = database.read_query("SELECT * FROM interesting_posts WHERE username=%s", (self.username, ), con=mysql_con, close_con=False)
            if len(interesting_posts) >= config.MAX_INTERSTING_POSTS:
                break                   

            # 1 Step: get top 10 profiler categories
            top_cats = []       
            cat = self.category.copy()      
            while len(top_cats) < 10:
                highest = (0, -1) # (value, cat_index)
                for index, x in enumerate(cat):
                    if highest[1] == -1 or x > highest[0]:
                        # first or better
                        highest = (x, index)

                top_cats.append(highest)
                cat[highest[1]] = 0
            
            # 2 Step: get 35 posts and prepare SVC data
            x = []
            y = []
            offset = random.randint(0, config.statics.LATEST_POSTS_START_LIMIT - 50) # random offset
            posts = database.read_query("SELECT * FROM latest_posts LIMIT " + str(offset) + ", 50;", (), con=mysql_con, close_con=False)
            while len(y) < 35:
                p = random.choice(posts)
                author, permlink, category, timestamp = p

                category = [float(x) for x in category.split(' ')]
                arr = []
                for _, index in top_cats:
                    arr.append(category[index])

                x.append(arr)
                y.append(f"{author}/{permlink}")
            del posts
                
            # 3 Step: make SVC and predict_proba            
            clss = SVC(kernel='poly', probability=True)
            clss.fit(x, y)
            c = [item[0] for item in top_cats]
            y_pred = clss.predict_proba([c])[0]

            # 4 Step: Check results and enter
            for index, pred in enumerate(y_pred):
                if pred >= config.INTERESTING_FACTOR:
                    # Found good one, enter
                    author = y[index].split('/')[0]
                    permlink = y[index].split('/')[1]

                    exists = database.read_query("SELECT author FROM interesting_posts WHERE username=%s AND author=%s AND permlink=%s;",
                                                (self.username, author, permlink), con=mysql_con, close_con=False)
                    if len(exists) > 0:
                        # Already listed --> Next one
                        continue

                    result = database.commit_query("INSERT INTO interesting_posts(username, author, permlink) VALUES (%s, %s, %s);",
                                                (self.username, author, permlink), con=mysql_con, close_con=False)
                    if result < 1:
                        # Error
                        print("[WARNING] Can't insert an interesting post!")
                        time.sleep(5)

        self.update_timestamp()


    @staticmethod
    def remove_old_profiler():
        con = config.get_connection()
        
        while 1:
            # wait
            time.sleep(30)


            # Get oldest profilers (10)
            profilers = database.read_query("SELECT username, timestamp FROM profiler ORDER BY timestamp ASC LIMIT 10;", (), con=con, close_con=False)
            
            for username, timestamp in profilers:
                timestamp = datetime.strptime(timestamp, "%d.%m.%YT%H:%M:%S")

                if timestamp < (datetime.utcnow() - timedelta(hours=config.PROFILER_DELETE_TIME)):
                    # To old --> remove
                    database.commit_query("SET SQL_SAFE_UPDATES = 0;", (), con=con, close_con=False)
                    database.commit_query("DELETE FROM profiler WHERE username=%s;", (username, ), con=con, close_con=False)
                    
                    # Remove interesting Posts
                    database.commit_query("DELETE FROM interesting_posts WHERE username=%s;", (username, ), con=con, close_con=False)

            