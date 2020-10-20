import config as conf
import helper
import hive

from gensim.models import word2vec
import multiprocessing
from tqdm import tqdm
import matplotlib.pyplot as plt

import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException
from beem.vote import AccountVotes

import os
import time
from datetime import datetime, timezone
import random
from threading import Thread

#   --- Neural networks ---

class WordEmbedding():
    def __init__(self):
        if os.path.exists(conf.WORD2VEC_PATH):
            # Try to load existent model
            try:
                self.model = word2vec.Word2Vec.load(conf.WORD2VEC_PATH)
                print("[INFO] Loaded Word2Vec Model")
            except  EOFError:
                # File is empty/corrupted
                print("[FAILED] Word2Vec Savefile is empty/corrupted. Create one manually or restart...")
                os.remove(conf.WORD2VEC_PATH)
                exit()
        else:
            # Create model
            test_sentence = [['Krypton', 'is', 'awesome']]
            cores = multiprocessing.cpu_count()

            self.model = word2vec.Word2Vec(test_sentence, iter=10, min_count=1,
                                             size=conf.EMBEDDING_DIM, workers=cores - 1)
            self.model.save(conf.WORD2VEC_PATH)
            print("[INFO] Created and saved new Word2Vec Model")

    def train_model(self, html = None, text = None, sentences = []):
        if html is not None:
            # Html to text and add to text
            if text is None:
                text = ''
            text += helper.html_to_text(html)

        if text is not None:
            text = helper.pre_process_text(text)

            for s in text.split('.'):
                # split in sentences and then in words: [['Hello','Christopher'], ['Im', 'cool']]
                sentences.append(s.split())

        if len(sentences) > 0:
            # Train word2vec
            self.model.build_vocab(sentences, update=True)
            self.model.train(sentences, total_examples=self.model.corpus_count, epochs=30)
            self.model.save(conf.WORD2VEC_PATH)
        
    def vectorize_text(self, html = None, text = None, train_unknown = False):
        if html is not None:
            # Html to text and add to text
            if text is None:
                text = ''
            text += helper.html_to_text(html)

        if text is not None:
            text = helper.pre_process_text(text)

            if train_unknown:
                self.train_model(text=text)

            # Create wordmap
            text = text.replace('.', ' ')
            words = list(filter(lambda x: x in self.model.wv.vocab, text.split()))
            
            #vectorize
            if len(words) >= 5:
                return T.Tensor([[self.model.wv.word_vec(w) for w in words]]).to(conf.device)
        
        
        return None


class TextCNN(nn.Module):
    def __init__(self):
        super(TextCNN, self).__init__()

        self.convs = nn.ModuleList([
                    nn.Conv2d(1, conf.KERNEL_NUM, (i, conf.EMBEDDING_DIM)) for i in conf.WINDOW_SIZES ])

        self.dropout = nn.Dropout(0.15)
        self.fc = nn.Linear(conf.KERNEL_NUM * len(conf.WINDOW_SIZES), len(conf.CATEGORIES))

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
        x = self.fc(x)
        x = F.softmax(x, dim = 1)

        return x

    @staticmethod
    def load_model():
        model = TextCNN()
        if os.path.exists(conf.TEXTCNN_PATH):
            model.load_state_dict(T.load(conf.TEXTCNN_PATH))

        return model.to(conf.device)

    @staticmethod
    def save_model(model):
        model.to('cpu')
        T.save(model.state_dict(), conf.TEXTCNN_PATH)
        model.to(conf.device)


#   --- Usecases for networks ---

class WordEmbeddingTrainer():
    def __init__(self, model : WordEmbedding):
        self.model = model
        self.dataset = sorted(helper.load_train_data(), key=lambda k: random.random())

    def train(self):
        # SUPERVISED LEARNING
        print("[INFO] Train Word2Vec model...")
        for item in tqdm(self.dataset, desc='Word2Vec Training'):
            # train from dataset
            if 'new_words' not in item:
                post = hive.get_post_json(item['url'])

                if post['body'] == '':
                    # Error occured
                    continue

                self.model.train_model(html=post['body'], text=post['title'] + '.')
               
        print("[INFO] Trained Word2Vec model succesfully!")

        # return newest, fully trained model
        return self.model

                
class Trainer():
    def __init__(self, model : TextCNN, embedding : WordEmbedding, train_word2vec = False):
        self.model = model
        self.embedding = embedding

        if train_word2vec:
            word2vec_trainer = WordEmbeddingTrainer(self.embedding)
            self.embedding = word2vec_trainer.train()
            del word2vec_trainer
            
        self.criterion = nn.BCELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=conf.LEARNING_RATE)

        self.dataset = helper.load_train_data()

    def train(self, epochs : int):
        # Supervised learning
        print("[INFO] Train TextCNN...")
        average_losses = []
        self.model.train()

        try:
            for e in range(epochs):
                # randomize list
                self.dataset = sorted(self.dataset, key=lambda k: random.random())
                epoch_loss = 0
                for item in self.dataset:
                    post = hive.get_post_json(item['url'])

                    if post['body'] == '':
                        # Error
                        continue

                    # Get tags
                    categories = item['categories']
                    if len(categories) == 0:
                        metadata = post['json_metadata']
                        categories = metadata['tags']

                    self.optimizer.zero_grad()

                    # Calc values
                    _input = self.embedding.vectorize_text(html=post['body'], text=post['title'] + ". ")
                    if _input is None:
                        continue
                    _output = self.model(_input)

                    # Target Tensor
                    _target = [0 for x in conf.CATEGORIES]
                    for index, category in enumerate(conf.CATEGORIES):
                        for tag in categories:
                            if tag == category:
                                _target[index] = 1

                    _target = T.Tensor([_target]).to(conf.device)

                    # Optimize                
                    loss = self.criterion(_output, _target)
                    epoch_loss = (epoch_loss + loss.item()) / 2
                    loss.backward()
                    self.optimizer.step()

                print(f"Epoch: {e}  Loss: {epoch_loss}")
                average_losses.append(epoch_loss)

                if len(average_losses) >= 2 and average_losses[-2] >= average_losses[-1]:
                    # Save if it is better than a previous one
                    TextCNN.save_model(self.model)

        except KeyboardInterrupt:
            print("[INFO] Ending training...")
        
        # Make diagram
        plt.plot(average_losses)
        plt.savefig('data/Training_Loss.png')
        plt.show()

        print("[INFO] Training ended succesfully.")
        return self.model

    def train_alone(self, save_every=50):
        print("[INFO] Train TextCNN (alone)...")
        self.model.train()
        counter = 0
        while True:
            try:
                tag = random.choice(conf.CATEGORIES)
                posts = hive.get_trending_posts_by_tags(tag=tag, limit=25)     
                if len(posts) == 0:
                    posts = hive.get_new_posts_by_tags(tag=tag, limit=25)          
                if len(posts) == 0:
                    # No posts found
                    print("No posts could be found: " + tag)
                    continue

                post = random.choice(posts)
                _input = self.embedding.vectorize_text(html=post['body'], text=post['title'] + ". ")
                if _input is None:
                    continue
                _output = self.model(_input)

                metadata = post['json_metadata']
                categories = metadata['tags']

                # Target Tensor
                _target = [0 for x in conf.CATEGORIES]
                for index, category in enumerate(conf.CATEGORIES):
                    for tag in categories:
                        if tag in category:
                            # in because politic is politics, mentalhealth, ...
                            _target[index] = 1

                _target = T.Tensor([_target]).to(conf.device)

                # Optimize                
                loss = self.criterion(_output, _target)
                loss.backward()
                self.optimizer.step()
                
                counter += 1
                if counter % save_every:
                    # save
                    TextCNN.save_model(self.model)

                print(f"Loss: {loss}    Index: {counter}    Categories: {' '.join(categories)}  Permlink: @{post['author']}/{post['permlink']}")
            except KeyboardInterrupt:
                print("Do you want to exit?")
                if 'y' in input('-->').lower():
                    TextCNN.save_model(self.model)
                    break
        return self.model


class Profiler():
    def __init__(self, username : str):
        self.username = username
        self.data = [0 for i in conf.CATEGORIES]
        self.data_lenght = 0

        self.account = Account(username, blockchain_instance=Hive())# node=conf.HIVE_NODES[5]
        

        # Post-Check Thread
        self.post_thread = Thread(target=self.check_posts)
        self.post_thread.daemon = True
        self.post_thread.name = f"Posts&Votes by {username}"
        self.post_thread.start()

        # Vote-Check Thread
        self.vote_thread = Thread(target=self.check_votes)
        self.vote_thread.daemon = True
        self.vote_thread.name = f"Votes by {username}"
        #self.vote_thread.start()

        self.reset_last_interaction()

    def reset_last_interaction(self):
        self.last_interaction = datetime.now(timezone.utc).replace(tzinfo=None)

    def add_data(self, _output, factor = 1):
        # add data
        l = _output.data[0].tolist()

        if self.data[0] == 0:
            # first data
            self.data = l
        else:
            # average data
            self.data = [((self.data[i] + l[i] * factor) / (1 + factor)) for i in range(len(self.data))]
        
        self.data_lenght += 1
        self.reset_last_interaction()

    def check_posts(self):
        for comment in self.account.history_reverse(only_ops=['comment']):
            if comment['author'] != self.username:
                continue
            
            _input = conf.statics.WordEmbedding.vectorize_text(html=comment['body'], text=comment['title'] + ". ")
            if _input is None:
                continue
            
            _output = conf.statics.TextCNN(_input).cpu()
            self.add_data(_output, factor=1)

            # wait for next request --> Prevent overflow
            time.sleep(0.2)
        self.check_votes()

    def check_votes(self):
        for vote in self.account.history_reverse(only_ops=['vote']):
            if vote['voter'] == self.username and vote['voter'] != vote['author']:
                # If I am the voter and it is not my post
                c = Comment(f"@{vote['author']}/{vote['permlink']}", blockchain_instance=Hive())# node=conf.HIVE_NODES[5]
                
                # vectorize
                _input = conf.statics.WordEmbedding.vectorize_text(html=c.body, text=c.title + ". ")
                if _input is None:
                    continue

                _output = conf.statics.TextCNN(_input).cpu()
                self.add_data(_output)

                # wait for next request --> Prevent overflow
                time.sleep(0.2)

