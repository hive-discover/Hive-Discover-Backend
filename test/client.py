import socket
import json
import time

available_categories = ['politic', 'technology', 'art', 'animal', 'music', 'travel', 'fashion',
              'gaming', 'purpose', 'food', 'wisdom', 'comedy', 'crypto', 'sports', 'beauty', 'fitness',
              'business', 'lifestyle', 'nature', 'tutorial', 'photography', 'story', 'news', 'health',
              'coding', 'education', 'introduceyourself', 'science', 'film', 'challenge', 'gardening', 'hive',
              'history', 'society']
              # maybe add: health, coding, education, introduceyourself, science, film, challenge, gardening, hive

buffer = json.dumps({"cmd" : "ping", "username" : "christopher2002"}).encode('utf-8')
host_ip = socket.gethostbyname(socket.gethostname())

c = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
c.connect((host_ip, 4156))


c.send(str(len(buffer)).encode('utf-8'))
c.recv(2)
c.send(buffer)

# Response

lenght = int(c.recv(10).decode('utf-8'))
c.send('OK'.encode('utf-8'))
data = c.recv(lenght).decode('utf-8')
print(data)


# add train data
while True:
    error = False
    url = input('URL=')
    categories = input('CATEGORIES=').split()
    for cat in categories:
        if cat not in available_categories:
            print(f"{cat} not found. Retry")
            print(available_categories)
            error = True
            break
    
    if error:
        continue

    if 'n' in input('new_words (y/n)=').lower():
        buffer = json.dumps({"cmd" : "add_data", "url" : url, "categories" : categories, "new_words" : "False"}).encode('utf-8')
    else:
        buffer = json.dumps({"cmd" : "add_data", "url" : url, "categories" : categories}).encode('utf-8')

    c.send(str(len(buffer)).encode('utf-8'))
    c.recv(2)
    c.send(buffer)

    lenght = int(c.recv(10).decode('utf-8'))
    c.send('OK'.encode('utf-8'))
    data = c.recv(lenght).decode('utf-8')
    print(data)
exit()

# Get posts
while True:
    try:
        buffer = json.dumps({"cmd" : "get_posts"}).encode('utf-8')
        c.send(str(len(buffer)).encode('utf-8'))
        c.recv(2)
        c.send(buffer)

        lenght = int(c.recv(10).decode('utf-8'))
        c.send('OK'.encode('utf-8'))
        data = c.recv(lenght).decode('utf-8')
        print(data)

        time.sleep(5)
    except KeyboardInterrupt:
        break

c.close()