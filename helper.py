import config as conf

from bs4 import BeautifulSoup
import urllib.request
import re
import os
import json


#   Train data

def load_train_data():
    with open('data/training_set.json', 'r') as file:
        dataset = json.load(file)
    return dataset


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




from OpenSSL import crypto, SSL
def cert_gen(
    emailAddress="emailAddress",
    commonName="commonName",
    countryName="NT",
    localityName="localityName",
    stateOrProvinceName="stateOrProvinceName",
    organizationName="organizationName",
    organizationUnitName="organizationUnitName",
    serialNumber=0,
    validityStartInSeconds=0,
    validityEndInSeconds=10*365*24*60*60,
    KEY_FILE = "private.key",
    CERT_FILE="selfsigned.crt"):
    #can look at generated file using openssl:
    #openssl x509 -inform pem -in selfsigned.crt -noout -text
    # create a key pair
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 4096)
    # create a self-signed cert
    cert = crypto.X509()
    cert.get_subject().C = countryName
    cert.get_subject().ST = stateOrProvinceName
    cert.get_subject().L = localityName
    cert.get_subject().O = organizationName
    cert.get_subject().OU = organizationUnitName
    cert.get_subject().CN = commonName
    cert.get_subject().emailAddress = emailAddress
    cert.set_serial_number(serialNumber)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(validityEndInSeconds)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha512')
    with open(CERT_FILE, "wt") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("utf-8"))
    with open(KEY_FILE, "wt") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode("utf-8"))

#cert_gen()