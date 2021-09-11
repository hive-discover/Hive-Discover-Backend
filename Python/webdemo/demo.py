import sys, os
sys.path.append(os.getcwd() + "/.")

from network import TextCNN
from config import *

import streamlit as st


RANDOM_POSTS = [
    ("@ericvancewalton", "/never-forget-what-s-become-of-post-9-11-america"),
    ("@doitvoluntarily", "/singapore-researchers-uncover-bluetooth-vulnerabilities-that-could-impact-billions"),
    ("@lockhart", "/huawei-continue-harmony-os-campaign"),
    ("@antoniojoseha", "/how-safe-it-is-sharing-our-information"),
    ("@natichi", "/daily"),
    ("@daring-celt", "/autumn-sketches-3")
]


USER_INPUT = {
    "author" : "",
    "permlink" : "",
    "min_percentage" : 10,
    "wordvec_url" : "https://api.hive-discover.tech:7879"
}

# **********************************
#   Header - Title, Caption, Instructions
# **********************************

st.title("Categorizer Demonstration")
st.caption("""
Suchen Sie passende HIVE Beiträge und geben Sie dann den Author sowie den Permlink an. Das neuronales Netz startet danach die arbeitet!
""")

col_btn_instructions, col_btn_random_post = st.columns(2)
btn_instruction = col_btn_instructions.button("Zeige Anleitung")
btn_random_post = col_btn_random_post.button("Zufälliger Beitrag")

if btn_instruction:
    # Show Instructions
    st.write("### Anleitung")
    st.write("""
    Suche Sie auf den unten verlinkten Seiten nach englischen Posts. Es dürfen auch Beiträge sein die Bilingual sind, also halb Englisch und halb eine andere Sprache beinhalten.
    Wenn Sie nun einen interessanten Artikel gefunden haben, können Sie dessen Author und Permlink rauskopieren und in der Sidebar einfügen. Die Informationen erhalten sie über die im Browser gezeigte URL. Ein Beispiel ist gegeben:
    """)
    st.write(f"**Author:** *@gaboamc2393*   **Permlink:** */new-cell-phone-and-pc-engesp*")
    st.image("webdemo/img/AuthorPermPeakd.JPG")
    st.write("Hier können sie (beispielsweise) gute Artikel finden:")
    col_1, col_2, col_3 = st.columns(3)
    col_1.write(" - [Technik](https://peakd.com/trending/tech)")
    col_2.write(" - [Kunst](https://peakd.com/trending/art)")
    col_3.write(" - [Nachrichten](https://peakd.com/trending/news)")
    col_1.write(" - [Politik](https://peakd.com/trending/politics)")
    col_2.write(" - [Essen](https://peakd.com/trending/food)")
    col_3.write(" - [Natur](https://peakd.com/trending/nature)")
    st.write("Sie können aber auch auf den Button 'Zufälliger Beitrag' klicken und hinterlegte Posts werden analysiert.")

# **********************************
#   Side Bar - Settings
# **********************************
sidebar = st.sidebar
sidebar.write("# Einstellungen ")

if "author" in st.session_state and "permlink" in st.session_state:
    if len(st.session_state.author) > 3 and len(st.session_state.permlink) > 3:
        USER_INPUT["author"] = st.session_state.author
        USER_INPUT["permlink"] = st.session_state.permlink

if btn_random_post:
    from random import choice
    USER_INPUT["author"], USER_INPUT["permlink"] = choice(RANDOM_POSTS)

txt_author = sidebar.text_input("Author", USER_INPUT["author"], key="author")
sidebar.text_input("Permlink", USER_INPUT["permlink"], key="permlink")
sidebar.slider("Mindest Prozentzahl", 0, 100, value=USER_INPUT["min_percentage"], key="min_percentage")
sidebar.text_input("WordVec-API URL", USER_INPUT["wordvec_url"], key="wordvec_url")
sidebar.write("Sie müssen nicht extra das Word2Vec-Model laden und lokal benutzen. Meine WordVec-API vereinfacht dies, indem das Modell per HTTP erreichbar ist. Es handelt sich dabei um die vortrainierte Fasttext-Datei von Facebook.")

USER_INPUT["author"] = st.session_state.author
USER_INPUT["permlink"] = st.session_state.permlink
USER_INPUT["min_percentage"] = st.session_state.min_percentage
USER_INPUT["wordvec_url"] = st.session_state.wordvec_url

# **********************************
#   Info Panel
# **********************************
info_container = st.container()

if len(USER_INPUT['author']) > 3 and len(USER_INPUT['permlink']) > 3:
    # Got Values
    info_container.write(f" **Author** : {USER_INPUT['author']}") 
    info_container.write(f" **Permlink** : {USER_INPUT['permlink']}")
    info_container.write(f" **Mindest Prozentzahl** : {USER_INPUT['min_percentage']}%")
else:
    # Warning
    info_container.warning("Es wurde kein Beitrag ausgewählt. Bitte tragen Sie in der Sidebar einen ein oder drücken Sie auf 'Zufälliger Beitrag'. Eine Anleitung ist oben zu finden")


# **********************************
#   Data Panel
# **********************************
data_container = st.container()
progress_bar = st.progress(0)

@st.cache()
def get_post(user_author : str, user_permlink : str):
    from beem.comment import Comment
    from beem.exceptions import ContentDoesNotExistsException
    
    # Generate authorperm
    authorperm = ""
    if "@" != user_author[0]:
        authorperm += "@"
    authorperm += user_author.lower()
    if "/" != user_permlink[0]:
        authorperm += "/"
    authorperm += user_permlink.lower()

    try:
        return Comment(authorperm)
    except ContentDoesNotExistsException:
        # Content Does Not Exist
        return None

@st.cache()
def download_image(url : str):
    import requests, io, cv2
    import numpy as np
    from PIL import Image

    response = requests.get(url)
    bytes_im = io.BytesIO(response.content)
    cv_im = cv2.cvtColor(np.array(Image.open(bytes_im)), cv2.COLOR_RGB2BGR)

    return cv_im

def get_plain_text(body : str) -> str:
    import markdown
    body = markdown.markdown(body)

    from bs4 import BeautifulSoup
    body = BeautifulSoup(body, features="html.parser").get_text()

    import re  
    body = body.lower()
    body = re.sub(r'^https?:\/\/.*[\r\n]*', ' ', body, flags=re.MULTILINE)  # Remove simple Links
    body = re.sub(r'[\(\[].*?[\)\]]', ' ', body, flags=re.MULTILINE) # Remove Markdown for Images and Links

    # Minimize \n\n
    while "\n\n" in body:
        body = body.replace("\n\n", "\n")

    # Replace some common Characters
    body = body.replace("$", " dollar ")
    body = body.replace("€", " euro ")
    body = body.replace("%", " percentage ")
    body = body.replace("&", " and ")
    return body

def tokenize(title : str, body : str) -> list:
    import spacy
    nlp = spacy.load('en_core_web_sm', disable=['parser', 'ner'])
    return [token.lemma_ for token in nlp(title + " \n\n\n " + body)]

def get_vectors(tokens : list) -> dict:
    import json, requests
    payload = json.dumps(tokens + ["(", "unknown", ")"])
    response = requests.request("POST", 
               USER_INPUT["wordvec_url"] + "/vector", 
                headers={'Content-Type': 'application/json'},
                data=payload)
    
    vectors = json.loads(response.text)["vectors"]

    # Decode vectors
    import base64, numpy as np
    for key in vectors.keys():
        d_bytes = base64.b64decode(vectors[key])
        vectors[key] = np.frombuffer(d_bytes, dtype=np.float64)

    return vectors

@st.cache()
def calc_output(vectored_text : list) -> tuple:
    # Get Input
    import torch as T
    _input = T.Tensor([vectored_text])
    _input_shape = list(_input.size())

    model, from_disk = TextCNN.load_model()

    # get Output
    _output = model(_input)
    _output_shape = list(_output.size())

    return (_output.tolist()[0], _input_shape, _output_shape, from_disk)

def main(user_author : str, user_permlink : str):
    # Get Comment
    comment = get_post(user_author, user_permlink)
    if not comment:
        data_container.error("Der Beitrag existiert nicht. Überprüfen Sie nochmal ihre Angaben. Sie finden Hilfe in der Anleitung oben!")
        return

    # Download img
    if "json_metadata" in comment and "image" in comment["json_metadata"] and len(comment["json_metadata"]["image"]) > 0:
        # Get Image
        cv_im = download_image(comment["json_metadata"]["image"][0])
    else:
        # Show placeholder Image
        cv_im = download_image("https://d34ip4tojxno3w.cloudfront.net/app/uploads/placeholder.jpg")

    # Show Comment
    data_container.write("### Dieser Beitrag wurde geladen:")
    img_col, text_col = data_container.columns(2)
    img_col.image(cv_im)
    text_col.write("**Titel:** " + comment["title"])
    text_col.write("**Tags:** " + " ".join(comment["json_metadata"]["tags"]))
    progress_bar.progress(10)

    # Get plain text
    body = get_plain_text(comment["body"])
    data_container.write(f"**Body Länge:** {len(body)}")
    progress_bar.progress(20)

    # Tokenizing
    tokens = tokenize(comment["title"], body)
    progress_bar.progress(35)
    
    # Get Unique tokens
    unique_tokens = set(tokens[::])
    data_container.write(f"**Einzelne Wörter:** {len(unique_tokens)}")

    # Get vectors 
    @st.cache()
    def make_vectors(unique_tokens, tokens):
        vectors = get_vectors(list(unique_tokens))

        # Vector the text
        vectored_text = []
        known_tokens, unknown_tokens = 0, 0
        for t in tokens:
            if t in vectors:
                vectored_text.append(vectors[t])
                known_tokens += 1 
            else:
                vectored_text += [vectors["("], vectors["unknown"], vectors[")"]]
                unknown_tokens += 1

        return (vectored_text, known_tokens, unknown_tokens)

    vectored_text, known_tokens, unknown_tokens = make_vectors(unique_tokens, tokens)
    data_container.write(f"**Bekannte Wörter:** {known_tokens}")
    data_container.write(f"**Unbekannte Wörter**: {unknown_tokens}")
    progress_bar.progress(75)
    
    # Calc
    _output, _input_shape, _output_shape, from_disk = calc_output(vectored_text)
    data_container.write(f"**Input Shape:** {_input_shape}")

    if from_disk:
        data_container.write("**TextCNN** wurde erfolgreich geladen")
    else:
        data_container.error("TextCNN konnte nicht geladen werden!")
        data_container.war("Das Model ist untrainiert. Daher sind unpräzise Ergebnisse möglich")

    data_container.write(f"**Output Shape:** {_output_shape}")
    progress_bar.progress(95)

    # Prepare Pie- and BarChart data
    piebarchart_data_sizes = []
    piebarchart_data_labels = []
    for index, val in enumerate(_output):
        val *= 100
        if val >= USER_INPUT["min_percentage"]:
            piebarchart_data_sizes.append(val)
            piebarchart_data_labels.append(CATEGORIES[index][0])


    # Make PieChart
    import matplotlib.pyplot as plt
    fig1, ax1 = plt.subplots()
    ax1.pie(piebarchart_data_sizes, labels=piebarchart_data_labels, autopct='%1.1f%%')
    ax1.axis('equal') 
    data_container.write("## Kuchendiagramm der Top-Werte:")
    data_container.pyplot(fig1)

    # Make BarChart
    fig1, ax1 = plt.subplots()
    x_pos = [i for i, _ in enumerate(piebarchart_data_labels)]
    ax1.bar(x_pos, piebarchart_data_sizes)
    plt.xticks(x_pos, piebarchart_data_labels)
    data_container.write("## Balkendiagramm der Top-Werte:")
    data_container.pyplot(fig1)

    # Make DataFrame
    import pandas as pd
    df = pd.DataFrame({
        "Kategorien" : [cat[0] for cat in CATEGORIES], 
        "Werte (roh)" : _output, 
        "Werte (Prozent)" : [x * 100 for x in _output] })
    data_container.write("## Alle Werte:")
    data_container.write("Sortierbar über einem Klick auf dem Spaltenname")

    # Color DataFrame
    radio_colored_dataframe = data_container.checkbox("Färbung", value=True)
    if radio_colored_dataframe:
        def cell_color(value):
            if value >= USER_INPUT["min_percentage"]:
                return f'background-color: rgb(45, 134, 45, {value / 100 + 0.05});'
            else:
                return f'background-color: rgb(255, 51, 51, {1 - value / 10 + 0.05});'  

        df = df.style.applymap(cell_color, subset=['Werte (Prozent)'])

    data_container.dataframe(df)

    progress_bar.progress(100)

if len(USER_INPUT['author']) > 3 and len(USER_INPUT['permlink']) > 3:
    main(USER_INPUT["author"], USER_INPUT["permlink"])