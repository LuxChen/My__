from MyThread import MyThread
import requests
from bs4 import BeautifulSoup
import base64

sub_url = [
    # "http://122.225.207.101:8080/ipns/k2k4r8kms1l1k3wljk4o8eopnb2dltfvh8pypr0zkeyjunyagft3aqvs/",
    # "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
    {'raw': "https://raw.fastgit.org/freefq/free/master/v2"},
    {'raw': "https://freefq.neocities.org/free.txt"},
    {'raw': "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config.txt"},
    {'code': "https://github.com/mianfeifq/share"},
    # {'raw': "https://raw.githubusercontent.com/mheidari98/.proxy/main/all"},
    # {'code': "https://github.com/mksshare/mksshare.github.io/blob/main/README.md"},
    # {'raw': "https://raw.fastgit.org/Pawdroid/Free-servers/main/sub"},
]

newlinks = []


def contents_appending(result):
    global newlinks
    if result:
        newlinks += result.split()


def check_link(params):
    url = params[0]
    try:
        for k, v in url.items():
            rq = requests.get(v, timeout=5000)
            if k == 'code':
                source_content = rq.content.decode(encoding='utf-8')
                soup = BeautifulSoup(source_content, 'html.parser')
                code = soup.find_all('code')[-1]
                filecontent = code.get_text()
                print("Read node link on sub " + v)
            else:
                if (rq.status_code != 200):
                    print("[GET Code {}] Download sub error on link: ".format(
                        rq.status_code) + v)
                print("Get node link on sub " + v)
                filecontent = base64.b64decode(rq.content).decode("utf-8")
            return filecontent
    except Exception as ex:
        print(ex)
        print("[Unknown Error] Download sub error on link: " +
              [this_v for this_v in url.values()][0])


threador = MyThread(check_link, sub_url, contents_appending, len(sub_url))
threador.execute()
with open('links.txt', 'r') as f:
    oldlinks = f.read().split()
    append_new_links = set(newlinks) - set(oldlinks)
    new_str = "\n".join(append_new_links)
    with open('newlinks.txt', 'w') as nf:
        nf.write(new_str)
with open('links.txt', 'a') as f:
    f.write(new_str)
