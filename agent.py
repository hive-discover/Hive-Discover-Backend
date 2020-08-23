import config as conf
from helper import *

import numpy as np
import matplotlib.pyplot as plt

from beem import Hive
from beem.blockchain import Blockchain

import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

import random, time
import json
import os
from threading import Thread
from datetime import datetime, timezone

# Text Embedding & Word2Vec

class Trainer():
    def __init__(self, model, embedding):
        self.model = model
        self.embedding = embedding

        self.criterion = nn.BCELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=conf.LEARNING_RATE)

        self.dataset = load_train_dataset_file()

    def train(self, epochs, retrain_word2vec=False):
        if retrain_word2vec:
            print('Start training word2vec model')
            self.embedding.train_model_dataset()

        self.model.train()
        average_losses = []

        print("Start text training...")
        for e in range(epochs):
            self.dataset = sorted(self.dataset, key=lambda k: random.random())
            epoch_losses = 0
            try:
                for item in self.dataset:   
                    # Get Post data             
                    post = get_hive_post_json(item['url'])
                    if post['body'] == '':
                        # Error occured while getting
                        # post json --> simply next row
                        continue
                    categories = item['categories']
                    if len(categories) == 0:
                        metadata = post['json_metadata']
                        categories = metadata['tags']
                    
                    if e == 0 and retrain_word2vec == True:
                        if 'new_words' not in item:
                            self.embedding.train_model(html=post['body'], text=post['title'] + ". ")

                    self.optimizer.zero_grad()

                    # Vectorize Text             
                    _input = self.embedding.text_vectorization(html=post['body'], text=post['title'] + ". ")
                    _output = self.model(_input)

                    # Making the target Tensor
                    _target = [0 for x in conf.CATEGORIES]
                    for index, category in enumerate(conf.CATEGORIES):
                        for tag in categories:
                            if tag == category:
                                _target[index] = 1

                    _target = T.Tensor([_target]).to(conf.device)

                    # Optimize                
                    loss = self.criterion(_output, _target)
                    epoch_losses += loss.item()
                    loss.backward()
                    self.optimizer.step()
                
                average_losses.append(epoch_losses / len(self.dataset))
                print(f'Epoch: {e + 1}   Average Loss: {average_losses[-1]}')
                if len(average_losses) >= 2 and average_losses[-2] >= average_losses[-1]:
                    network.save_model(self.model)

            except KeyboardInterrupt:
                print(f"[INFO] Keyboard Interrupt. Epoch: {e + 1}/{epochs}")

        plt.plot(average_losses)
        plt.savefig('data/Training_Loss.png')
        plt.show()
        return self.model

class Tester():
    def __init__(self, model, embedding):
        self.model = model
        self.embedding = embedding
        self.dataset = load_test_dataset_file()

    def run(self):
        self.model.eval()
        for item in self.dataset:
            post = get_hive_post_json(item['url'])
            if post['body'] == '':
                # Error occured while getting
                # post json --> simply next row
                continue

            # Vectorize Text           
            _input = self.embedding.text_vectorization(html=post['body'], text=post['title'] + ". ")
            _output = self.model(_input)

            # Set categories
            categories = item['categories']
            if len(categories) == 0:
                metadata = post['json_metadata']
                categories = metadata['tags']

            # Making target
            _target = [0 for x in conf.CATEGORIES]
            for index, category in enumerate(conf.CATEGORIES):
                for tag in categories:
                    if tag == category:
                        _target[index] = 1

            print('URL: ' + item['url'])
            print('TARGET:')
            print(_target)
            print('OUTPUT:')
            print(_output)

                    
# 

class DiscoverAdvisor():
    def __init__(self, username : str, model = None, embedding = None):
        self.running = True
        self.username = username
        self.interesting_posts = []

        # Set models                
        if model is None:
            self.model = network.load_model()
        else:
            self.model = model
        self.model.eval()
        if embedding is None:
            self.embedding = network.WordEmbedding()
        else:
            self.embedding = embedding
        #self.profiler = network.ProfileSVM()
        self.data = []

        # Start Threads
        self.check_voting_thread = Thread(target=self.check_votings)
        self.check_voting_thread.name = f'Votes - {username}'
        self.check_voting_thread.daemon = True
        self.check_voting_thread.start()

        self.check_posts_thread = Thread(target=self.check_posts)
        self.check_posts_thread.name = f'Posts - {username}'
        self.check_posts_thread.daemon = True
        self.check_posts_thread.start()

        self.check_posts_thread = Thread(target=self.choose_interesting_posts)
        self.check_posts_thread.name = f'Discover - {username}'
        self.check_posts_thread.daemon = True
        self.check_posts_thread.start()

    def check_votings(self):
        voting_list = get_all_hive_votes(self.username)

        for permlink, author in reversed(voting_list):
            # Categorize liked texts and add it to SVC
            if self.running is False:
                break
            
            vector = self.analyze_post(permlink, author)
            if vector is not -1:
                if self.running:
                    self.data.append(vector.data[0].tolist())
                

    def check_posts(self):
        posts_list = get_all_hive_posts(self.username)

        for permlink, author in reversed(posts_list):
            # Categorize self writen texts and add it to SVC
            if self.running is False:
                break

            vector = self.analyze_post(permlink, author)
            if vector is not -1:
                self.data.append(vector.data[0].tolist())

    def analyze_post(self, permlink : str, author = ''):
        if author == '':
            author = self.username

        # Get post and vectorize it
        post = get_hive_post(permlink, author)
        if post['parent_author'] is not '':
            return -1
        _input = self.embedding.text_vectorization(html=post['body'], text=post['title'] + ". ", train_unknown=False)
        
        if _input == None:
            return -1

        # Categorize
        _output = self.model(_input)

        # return model output
        return _output.cpu()
                
    def choose_interesting_posts(self):
        while len(self.data) < conf.PROFILER_MINUMUM_DATA_LENGTH or len(conf.LATEST_POSTS) < 5:
            time.sleep(0.2)              

        while self.running:
            # Get random post
            rnd_int = np.random.randint(0, len(conf.LATEST_POSTS))
            post = conf.LATEST_POSTS[rnd_int]

            if post not in self.interesting_posts:
                # Split data and calculate differnece
                # Over given factor --> append to list
                _, _, category, _ = post

                for x in self.data:
                    diff = np.array(x) - np.array(category)
                    value = 0
                    for a in diff:
                        if a < 0:
                            a = a * -1
                        value += a

                    if value <= conf.PROFILER_INTERESTING_FACTOR:
                        self.interesting_posts.append(post)
                        break
                    
        
                
class LatestPostsManager():
    def __init__(self, model = None, embedding = None):
        self.chain = Blockchain(blockchain_instance=Hive())
        self.posts = []

        if model is None:
            self.model = network.load_model()
        else:
            self.model = model

        if embedding is None:
            self.embedding = network.WordEmbedding()
        else:
            self.embedding = embedding

        self.run_thread = Thread(target=self.run)
        self.run_thread.name = 'Get & Categorize Posts'
        self.run_thread.daemon = True
        self.run_thread.start()

    def get_posts_from_block(self, block):
        posts = []
        for op in block.operations:
            if op['type'] == 'comment_operation':
                action = op['value']
                if action['parent_author'] == '':
                    # found post --> Categorize
                    _input = self.embedding.text_vectorization(html=action['body'], text=action['title'] + ". ")
                    if _input is None:
                        # to short or error
                        continue

                    _output = self.model(_input).cpu()
                    posts.append((action['permlink'], action['author'], _output.data[0].tolist(), block["timestamp"]))
        return posts

    def cleanup_post_list(self):
        # remove old ones
        # only the first ones because they were sorted
        # old posts are first
        if len(conf.LATEST_POSTS) <= 5:
            return

        for permlink, author, category, timestamp in conf.LATEST_POSTS[:5]:
            delta = datetime.now(timezone.utc) - timestamp
            if delta.days > 5:
                conf.LATEST_POSTS.remove((permlink, author, category, timestamp))

    def run(self):
        current_num = self.chain.get_current_block_num() - int(60*60*24*5/3) # Get all posts from the last 5 days
        while True:     
            if current_num < self.chain.get_current_block_num():              
                # if block is available
                for block in self.chain.blocks(start=current_num, stop=current_num):
                    conf.LATEST_POSTS += self.get_posts_from_block(block)
                        
                current_num += 1
            else:
                # wait until new block is created
                # Using time for cleanup
                self.cleanup_post_list()




        