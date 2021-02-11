from config import *

import torch as T
import torch.nn as nn
import torch.nn.functional as F

import fasttext

import os

EMBEDDING_DIM = 300
WINDOW_SIZES = (1, 2, 3, 5, 8)
KERNEL_NUM = 128


def get_all_vocabs_as_sentence()->list:
    '''Return a list of all vocabs inside word2vec for search'''
    return [str(w) for w in statics.FASTTEXT_MODEL.wv.vocab]#statics.WORD2VEC_MODEL.wv.vocab]


class TextCNN(nn.Module):
    def __init__(self):
        super(TextCNN, self).__init__()      
                      
        self.convs = nn.ModuleList([
                            nn.Conv2d(1, KERNEL_NUM, (i, EMBEDDING_DIM)) for i in WINDOW_SIZES ])
        self.dropout = nn.Dropout(0.15)
        
        self.fc1 = nn.Linear(KERNEL_NUM * len(WINDOW_SIZES), KERNEL_NUM)
        self.fc2 = nn.Linear(KERNEL_NUM, len(CATEGORIES))
        self.relu = nn.ReLU()

    def forward(self, x): 
        # Convs Layer
        xs = []
        for conv in self.convs:
            x2 = T.tanh(conv(x.unsqueeze(1)))
            x2 = T.squeeze(x2, -1)
            x2 = F.max_pool1d(x2, x2.size(2))
            x2 = self.dropout(x2)
            xs.append(x2)
        x = T.cat(xs, 2)
        
        # FC1
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))

        # FC2
        x = self.fc2(x)
        x = F.softmax(x, dim = 1)
        return x

    @staticmethod
    def load_model() -> tuple:
        '''
        Loads the TextCNN Model. Also from Disc (when available -> from_disc=true)
        Returns: tuple ( model : TextCNN, from_disc : bool )
        '''
        model = TextCNN()
        from_disc = False
        if os.path.exists(TEXTCNN_MODEL_PATH):
            model.load_state_dict(T.load(TEXTCNN_MODEL_PATH))
            from_disc = True

        return (model, from_disc)


class LangDetector():
    def __init__(self, load_model = True) -> None:
        '''Loads the lang-model'''
        self.model = None

        if load_model:
            # Load
            self.model = fasttext.load_model(LANG_FASTTEXT_MODEL)

    def predict_lang(self, text : str) -> list:
        '''
        Predict the language of a given text and return label of of predicted language.
        Returns in this way: [{"lang" : "en", "x" : 0.99}, ...]
        '''

        # predict returns something like(("label_1", "label_2"), array(0.4, 0.5))
        labels, scores = self.model.predict(text, k=3)

        # Get only langs that could be (score above 0.2)
        predictions = []
        for label, score in zip(labels, scores):
            if score > 0.2:
                predictions.append((label.replace("__label__", ""), score))


        return [{"lang" : label, "x" : score} for label, score in predictions]


        