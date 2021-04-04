from config import *
from bs4 import BeautifulSoup

import time
import re, string
import markdown

class helper:
    @staticmethod
    def init(load_nlp = True) -> None:     
        if load_nlp:
            import spacy
            helper.nlp = spacy.load("en_core_web_sm")
            import nltk
            nltk.download("wordnet")

    @staticmethod
    def html_to_text(html : str) -> str:
        '''Converts Markdown to html and html to plain text'''
        try:
            html = markdown.markdown(html)
        except:
            pass
        
        try:
            return BeautifulSoup(html, features="html.parser").findAll(text=True)
        except:
            return str(html)

    @staticmethod
    def pre_process_text(text : str, lmtz = None) -> str:
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

        # Lemmatize
        if lmtz is None:
            text = statics.LEMMATIZER.lemmatize(text)
        else:
            text = lmtz.lemmatize(text)

        return text

    @staticmethod
    def tokenize_text(text : str) -> list:
        '''Tokenize a text and return it'''
        # Prepare Text
        import ftfy    
        doc_text = ftfy.fix_text(text)

        # Tokenize
        doc = helper.nlp(doc_text)
        return [token.text for token in doc]
        
        # OLD
        import ftfy
        tok_text = [] 
        text = [ftfy.fix_text(text)]

        #Tokenising using SpaCy:
        for doc in helper.nlp.pipe(text, disable=["tagger", "parser","ner"]):
            tok = [t.text for t in doc if (t.is_ascii and not t.is_punct and not t.is_space)]
            if len(tok) > 1:
                tok_text.append(tok)

        if len(tok_text) > 0:
            return tok_text[0]
        else:
            return []

    @staticmethod
    def count_in_list(l : list, value) -> int:
        counter = 0
        for x in l:
            if x == value:
                counter += 1

        return counter

class Lemmatizer():
    def __init__(self):
        from nltk.stem.wordnet import WordNetLemmatizer
        self.lmmze = WordNetLemmatizer()
        self.working = False

    def lemmatize(self, text : str) -> str:
        while self.working:
            time.sleep(0.1)

        self.working = True
        text = self.lmmze.lemmatize(text)
        self.working = False
        return text
