from config import *

import torch as T
import torch.nn as nn
import torch.nn.functional as F

import os


EMBEDDING_DIM = 100
LEARNING_RATE = 0.001
WINDOW_SIZES = (2, 3, 4, 5)
KERNEL_NUM = 100


class TextCNN(nn.Module):
    def __init__(self):
        super(TextCNN, self).__init__()

        self.convs1 = nn.ModuleList([
                          nn.Conv2d(1, KERNEL_NUM, (i, EMBEDDING_DIM)) for i in WINDOW_SIZES ])
    
        self.dropout = nn.Dropout(0.15)
    
        self.hid = nn.Linear(KERNEL_NUM * 2, KERNEL_NUM)
        self.out1 = nn.Linear(KERNEL_NUM, KERNEL_NUM)
        self.out2 = nn.Linear(KERNEL_NUM, len(CATEGORIES))
        self.relu = nn.ReLU()

    def forward(self, x):
        # CONV1
        xs = [] 
        for conv in self.convs1:
            x2 = T.tanh(conv(x.unsqueeze(1)))
            x2 = T.squeeze(x2, -1)
            x2 = F.max_pool1d(x2, x2.size(2))
            x2 = self.dropout(x2)
            xs.append(x2)
        
        hidden = T.zeros(KERNEL_NUM)
        for x2 in xs:
            hidden = self.hid(T.cat((x2.squeeze(0).squeeze(1), hidden), 0))
            hidden = self.relu(hidden)

            out = self.relu(self.out1(hidden))
            out = self.out2(out).unsqueeze(0)

        return F.softmax(out, dim=1)


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



        