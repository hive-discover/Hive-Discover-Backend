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


def calc_percentages(arr):
    percs = []
    total_amount = 0
    for x in arr:
        total_amount += x
    
    for x in arr: # % = Anteil/Gesamt
        percs.append(float(x/total_amount))

    return percs


def get_top_elements(arr, amount):
    top_ones = []   
    arr = arr.copy()

    while len(top_ones) < amount:
        highest = (0, -1) # (value, arr_index)

        for index, x in enumerate(arr):
            if highest[1] == -1 or x > highest[0]:
                # first or better
                highest = (x, index)

        top_ones.append(highest)
        arr[highest[1]] = 0
    
    return top_ones