import config as conf
from helper import *

import matplotlib.pyplot as plt
import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import random
import json
import os


class Trainer():
    def __init__(self, model):
        self.model = model

        self.criterion = nn.BCELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=conf.LEARNING_RATE)

        self.dataset = load_train_dataset_file()

    def train(self, epochs, retrain_word2vec=False):
        self.model.train()
        embedding = network.WordEmbedding()
        average_losses = []

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
                        embedding.train_model(html=post['body'])

                    self.optimizer.zero_grad()

                    # Vectorize Text             
                    _input = embedding.text_vectorization(html=post['body'], text=post['title'] + ". ")
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
    def __init__(self, model):
        self.model = model
        self.dataset = load_test_dataset_file()

    def run(self):
        self.model.eval()
        embedding = network.WordEmbedding()
        for item in self.dataset:
            post = get_hive_post_json(item['url'])
            if post['body'] == '':
                # Error occured while getting
                # post json --> simply next row
                continue

            # Vectorize Text           
            _input = embedding.text_vectorization(html=post['body'], text=post['title'] + ". ")
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

                    

                
                   

                



        