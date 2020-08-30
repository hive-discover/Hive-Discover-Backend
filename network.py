import config as conf
import helper

from gensim.models import word2vec
import multiprocessing

import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from sklearn import svm
import numpy as np

from bs4 import BeautifulSoup
import os
import time
import csv

class WordEmbedding():
    def __init__(self):
        if os.path.exists(conf.WORD_2_VEC_SAVE_PATH):
            # Load existent model
            try:
                self.model = word2vec.Word2Vec.load(conf.WORD_2_VEC_SAVE_PATH)
                print("[INFO] Loaded Word2Vec Model")
            except EOFError:
                # File is empty
                print("[WARNING] Word2Vec Model file is empty. Creating new one...")
                os.remove(conf.WORD_2_VEC_SAVE_PATH)
                time.sleep(1.5)
        else:
            # Create new model
            test_sentence = [['Hello', 'World']]
            cores = multiprocessing.cpu_count()

            self.model = word2vec.Word2Vec(test_sentence, iter=10,
                                           min_count=1, size=conf.EMBEDDING_DIM,
                                           workers=cores - 1)
            self.model.save(conf.WORD_2_VEC_SAVE_PATH)
            print("[INFO] Created and saved Word2Vec Model")

    def train_model_dataset(self):
        sentences = []
        with open('data/articles.csv', 'r', encoding = 'cp850') as csv_file:
            # Loading articles
            reader = csv.reader(csv_file, delimiter=',')
            line_count = 0
            for row in reader:
                if line_count == 0:
                    # Column name line
                    line_count += 1
                    continue
                else:
                    line_count += 1
                    text = row[5].encode('ascii', 'ignore').decode('utf-8') 
                    text = helper.pre_process_text(text)
                    for sentence in text.split('.'):
                        sentences.append(sentence.split(' '))

        with open("data/train.tsv", encoding = 'cp850') as tsv_file:
            # loading Google train data
            read_tsv = csv.reader(tsv_file, delimiter="\t")
            line_counter = 0
            for row in read_tsv:
                if line_counter == 0:
                    line_counter += 1
                else:
                    #sentences.append(helper.pre_process_text(row[0]).split(' '))
                    line_counter += 1
        self.train_model(sentences=sentences)
            

    def train_model(self, text = None, html = None, sentences = None):
        if html is not None:
            # Parse HTML and extract only text
            soup = BeautifulSoup(html, features="html.parser")
            if text is None:
                text = ''
            text = soup.get_text()

        if text is not None:
            text = helper.pre_process_text(text)

            if sentences is None:
                sentences = []

            for s in text.split('.'):
                # Add list in list sentences
                sentences.append(s.split())
        
        if sentences is not None:
            # Finally Train our model
            self.model.build_vocab(sentences, update=True)
            self.model.train(sentences, total_examples=self.model.corpus_count, epochs=50)
            # Saving
            self.model.save(conf.WORD_2_VEC_SAVE_PATH)

    def text_vectorization(self, text = None, html = None, train_unknown = False):
        if html is not None:
            # Parse HTML and extract only text
            soup = BeautifulSoup(html, features="html.parser")
            if text is None:
                text = ''
            text += soup.get_text()

        if text is not None:
            # Pre process            
            text = helper.pre_process_text(text)

            if train_unknown:
                # Maybe train if some words 
                # are unknown
                self.train_model(text=text)

            # Create Wordlist and vectorize it
            # Previously be sure to filter out the unknown
            text = text.replace('.', ' ')
            words = list(filter(lambda x: x in self.model.wv.vocab, text.split()))
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


# Methods

def load_model():
    model = TextCNN()
    if os.path.exists(conf.TEXT_CNN_SAVE_PATH):
        model.load_state_dict(T.load(conf.TEXT_CNN_SAVE_PATH))
    
    return model.to(conf.device)

def save_model(model : TextCNN):
    model.to('cpu')
    T.save(model.state_dict(), conf.TEXT_CNN_SAVE_PATH)
    model.to(conf.device)

