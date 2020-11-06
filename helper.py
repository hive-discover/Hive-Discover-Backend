from bs4 import BeautifulSoup
import urllib.request
import re
import os
import json


#   Text processing

def html_to_text(html):
    soup = BeautifulSoup(html, features="html.parser")
    return soup.get_text()

def pre_process_text(text):
    # Process text to become word embedding friendly

    text = re.sub(r'^https?:\/\/.*[\r\n]*', ' ', text, flags=re.MULTILINE)  # Remove simple Links
    text = re.sub(r'[\(\[].*?[\)\]]', ' ', text, flags=re.MULTILINE) # Remove Markdown for Images and Links

    # Replace other characters
    text = text.replace('?', '.').replace('!', '.')
    text = text.replace('\n', '')
    text = text.replace('#', '').replace('-', ' ')
    text = text.replace("'", ' ').replace(", ", ' ').replace(':', '.').replace(';', ' ')
    text = text.replace('$ ', ' dollar ').replace(' $', ' dollar ')
    text = text.replace('€ ', ' euro ').replace(' €', ' euro ')
    text = text.replace('%', " percentage ")

    # Remove whitespaces
    while '  ' in text:
        text = text.replace('  ', ' ')

    text = text.replace(' .', '.')
    while '..' in text:
        text = text.replace('..', '.')

    # return lower
    return text.lower()

