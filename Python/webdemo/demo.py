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
    ("@greengalletti", "/espeng-emociones-un-accidente-surrealista-y-dramatico-con-un-ganador-inesperado-en-el-gp-de-monza-de-formula-1-emotions-a-surre"),
    ("@chops316", "/chops316-monday-morning-quarterback-2021-opening-night-let-s-go"),
    ("@wolfgangsport", "/top-5-cities-ranked-for-nfl-international-expansion"),
    ("@adhammer", "/some-fans-are-finally-understanding"),
    ("@fermentedphil", "/cape-gooseberries-the-plant-that"),
    ("@intoy.bugoy", "/goosebumps-experience-in-the-highest-summit-of-cebu-island-osmena-peak-dalaguete-cebu-philippines-or-lakwatsaniintoy-diary-00"),
    ("@edprivat", "/road-trip-to-marciac-france"),
    ("@macchiata", "/an-entire-day-of-food-adventure"),
    ("@obsesija", "/homemade-cheese-pie-recipe"),
    ("@natichi", "/form"),
    ("@armandosodano", "/marine-amphitheater-watercolor-on-paper-step-by-step"),
    ("@photovisions", "/norwegian-forest-into-the-forest"),
    ("@yashny", "/my-covid-19-vaccination-experience"),
    ("@derangedvisions", "/what-an-amazing-gaming-experience"),
    ("@wirago", "/new-world-open-beta-test"),
    ("@emuse", "/the-sims-4-my-experience-with-the-gaming-pack-strangerville"),
    ("@daltono", "/updmnsds"),
    ("@themarkymark", "/getting-started-with-hive-app-development"),
    ("@sarkodieeric1", "/cryptocurrency-portfolio-management"),
    ("@lockhart", "/razer-brings-the-hype-and-not-much-more"),
    ("@code-redex", "/top-5-tips-and-tricks-to-be-a-better-programmer"),
    ("@rbalzan79", "/space-technology-as-an-essential-tool-for-the-protection-of-our-environment"),
    ("@oscurity", "/what-the-petals-are-used"),
    ("@oscurity", "/the-pollen-to-the-microscope"),
    ("@lupafilotaxia", "/our-brain-and-its-particular-way-of-encoding-time"),
    ("@mauromar", "/new-giant-leap-towards-fusion-energy-nuevo-paso-de-gigante-hacia-la-energia-de-fusion"),
    ("@jorgebgt", "/a-new-rotary-detonation-space"),
    ("@jorgebgt", "/etna-grows-fast-geological-processes"),
    ("@mauromar", "/crispr-gene-editing-tool-successfully-tested-in-space-probada-con-exito-la-herramienta-de-edicion-genetica-crispr-en-el-espacio"),
    # d.buzz Posts
    ("@steemseph", "/8yy7drw59dc7mbgu0nxcpz"),
    ("@progressivechef", "/h0hk7g6hm2bxv3g7lqtouj"),
    ("@honeysaver", "/vryvpjtsfzxh6o3z6nfzff"),
    ("@demotruk", "/ezeoxbpszlmcjcdsnsz6ji"),
    ("@leveragetrading", "/s4zgi2w8d10ljrfjjx4nv0"),
    ("@manniman", "/gut18vbs1m2e2lfq5k7rzf"),
    ("@koenau", "/9a0go8dgkc1kfdh8bfaohe"),
    ("@tdctunes", "/tp5o2stay8gvy93a5gg3m8"),
]


USER_INPUT = {
    "author" : "",
    "permlink" : "",
    "min_percentage" : 10,
    "wordvec_url" : "https://word2vec.hive-discover.tech"
}

# **********************************
#   Header - Title, Caption, Instructions
# **********************************

st.title("Categorizer Demonstration")
st.caption("""
Search for content on HIVE and categorize it by our AI model. Just provide us the author and permlink in the left menu and we show what our AI thinks about that post!
""")

col_btn_instructions, col_btn_random_post = st.columns(2)
btn_instruction = col_btn_instructions.button("Show Introduction")
btn_random_post = col_btn_random_post.button("Random Post")

if btn_instruction:
    # Show Instructions
    st.write("### Introduction")
    st.write("""
    Below you can find some interesting topics for HIVE posts which can be categorized. In the best case, you enter english posts (because they are proceed at the best) but 
    bilingual posts are also possible when they contain atleast some english content.
    If you found something good, copy the author and permlink to our sidebar and the AI part begins. An example:
    """)
    st.write(f"**Author:** *@gaboamc2393*   **Permlink:** */new-cell-phone-and-pc-engesp*")
    st.image("webdemo/img/AuthorPermPeakd.JPG")
    st.write("Some good topics (example):")
    col_1, col_2, col_3 = st.columns(3)
    col_1.write(" - [Tech](https://peakd.com/trending/tech)")
    col_2.write(" - [Art](https://peakd.com/trending/art)")
    col_3.write(" - [News](https://peakd.com/trending/news)")
    col_1.write(" - [Politics](https://peakd.com/trending/politics)")
    col_2.write(" - [Food](https://peakd.com/trending/food)")
    col_3.write(" - [Nature](https://peakd.com/trending/nature)")
    st.write("You can also click on 'Random Post' to get a (nearly) random post from the HIVE blockchain")

# **********************************
#   Side Bar - Settings
# **********************************
sidebar = st.sidebar
sidebar.write("# Settings ")

if "author" in st.session_state and "permlink" in st.session_state:
    if len(st.session_state.author) > 3 and len(st.session_state.permlink) > 3:
        USER_INPUT["author"] = st.session_state.author
        USER_INPUT["permlink"] = st.session_state.permlink

if btn_random_post:
    from random import choice
    USER_INPUT["author"], USER_INPUT["permlink"] = choice(RANDOM_POSTS)

txt_author = sidebar.text_input("Author", USER_INPUT["author"], key="author")
sidebar.text_input("Permlink", USER_INPUT["permlink"], key="permlink")
sidebar.slider("Least Percentage", 0, 100, value=USER_INPUT["min_percentage"], key="min_percentage")
sidebar.text_input("WordVec-API URL", USER_INPUT["wordvec_url"], key="wordvec_url")
sidebar.write("""
You do not have to host your own Word2Vector API. We have a free one which is hosted on our server for this purpose.
""")

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
    info_container.write(f" **Least Percentage** : {USER_INPUT['min_percentage']}%")
else:
    # Warning
    info_container.warning("Nothing was entered. Have a look at the top for an introduction and then enter something good or click on 'Random Post'!")


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
    import requests, io
    from PIL import Image

    response = requests.get(url)
    bytes_im = io.BytesIO(response.content)

    return Image.open(bytes_im)

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
        data_container.error("This post does not exist. Please check your entered author/permlink. You will get help at the top!")
        return

    # Download img
    try:
        # Get Image
        cv_im = download_image(comment["json_metadata"]["image"][0])
    except:
        # Show placeholder Image
        cv_im = download_image("https://d34ip4tojxno3w.cloudfront.net/app/uploads/placeholder.jpg")

    # Show Comment
    data_container.write("### This post was choosed and loaded:")
    img_col, text_col = data_container.columns(2)
    img_col.image(cv_im)
    text_col.write("**Titel:** " + comment["title"])
    text_col.write("**Category:** " + comment["category"])
    text_col.write("**Tags:** " + ", ".join(comment["json_metadata"]["tags"]))
    text_col.write(f"Read the whole article [here](https://peakd.com/@{comment['author']}/{comment['permlink']})")
    progress_bar.progress(10)

    # Get plain text
    body = get_plain_text(comment["body"])
    data_container.write(f"**Body Length:** {len(body)}")
    progress_bar.progress(20)

    # Tokenizing
    tokens = tokenize(comment["title"], body)
    progress_bar.progress(35)
    
    # Get Unique tokens
    unique_tokens = set(tokens[::])
    data_container.write(f"**Unique Words:** {len(unique_tokens)}")

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
    data_container.write(f"**Known Words:** {known_tokens}")
    data_container.write(f"**Unknown Words**: {unknown_tokens}")
    progress_bar.progress(75)
    
    # Calc
    _output, _input_shape, _output_shape, from_disk = calc_output(vectored_text)
    data_container.write(f"**Input Shape:** {_input_shape}")

    if from_disk:
        data_container.write("**TextCNN** was successfully loaded")
    else:
        data_container.error("TextCNN cannot be loaded!")
        data_container.war("The AI model is currently untrained. Unprecise results are expected. Please contact us for help")

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
    data_container.write("## Piechart of the top results:")
    data_container.pyplot(fig1)

    # Make BarChart
    fig1, ax1 = plt.subplots()
    x_pos = [i for i, _ in enumerate(piebarchart_data_labels)]
    ax1.bar(x_pos, piebarchart_data_sizes)
    plt.xticks(x_pos, piebarchart_data_labels)
    data_container.write("## Barchart of the top results:")
    data_container.pyplot(fig1)

    # Make DataFrame
    import pandas as pd
    df = pd.DataFrame({
        "Categories" : [cat[0] for cat in CATEGORIES], 
        "Values (raw)" : _output, 
        "Value (Percentage)" : [x * 100 for x in _output] })
    data_container.write("## All Results:")
    data_container.write("Sortable by clicking the column name")

    # Color DataFrame
    radio_colored_dataframe = data_container.checkbox("Colouring", value=True)
    if radio_colored_dataframe:
        def cell_color(value):
            if value >= USER_INPUT["min_percentage"]:
                return f'background-color: rgb(45, 134, 45, {value / 100 + 0.05});'
            else:
                return f'background-color: rgb(255, 51, 51, {1 - value / 10 + 0.05});'  

        df = df.style.applymap(cell_color, subset=['Value (Percentage)'])

    data_container.dataframe(df)

    progress_bar.progress(100)

if len(USER_INPUT['author']) > 3 and len(USER_INPUT['permlink']) > 3:
    main(USER_INPUT["author"], USER_INPUT["permlink"])