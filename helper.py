from config import *

from bs4 import BeautifulSoup
import re
import string

import spacy
from ftfy import * 


nlp = spacy.load("en_core_web_sm")


def html_to_text(html : str) -> str:
    return BeautifulSoup(html).findAll(text=True)

def pre_process_text(text : str) -> str:
    '''Process Text to fit into models'''

    text = re.sub(r'^https?:\/\/.*[\r\n]*', ' ', text, flags=re.MULTILINE)  # Remove simple Links
    text = re.sub(r'[\(\[].*?[\)\]]', ' ', text, flags=re.MULTILINE) # Remove Markdown for Images and Links

    # Replace other characters
    text = text.replace('?', '.').replace('!', '.')
    text = text.replace('\n', ' ')
    text = text.replace('#', '').replace('-', ' ')
    text = text.replace("'", ' ').replace(", ", ' ').replace(':', '.').replace(';', ' ')
    text = text.replace('$ ', ' dollar ').replace(' $', ' dollar ')
    text = text.replace('€ ', ' euro ').replace(' €', ' euro ')
    text = text.replace('%', " percentage ")

    # Remove whitespaces
    while '  ' in text:
        text = text.replace('  ', ' ')

    # Remove multiple points
    text = text.replace(' .', '.')
    while '..' in text:
        text = text.replace('..', '.')

    text = text.lower()
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    text = re.sub(r'@\w+', '', text)  
    text = re.sub(r'[%s]' % re.escape(string.punctuation), ' ', text)
    text = re.sub(r'[0-9]', '', text)
    text = re.sub(r'\s{2,}', ' ', text)

    return text

def tokenize_text(text : str) -> list:
    '''Tokenize a text and return it'''
    tok_text = [] 
    text = [fix_text(text)]

    #Tokenising using SpaCy:
    for doc in nlp.pipe(text, n_threads=2, disable=["tagger", "parser","ner"]):
        tok = [t.text for t in doc if (t.is_ascii and not t.is_punct and not t.is_space)]
        if len(tok) > 1:
            tok_text.append(tok)
    if len(tok_text) > 0:
        return tok_text[0]
    else:
        return []




