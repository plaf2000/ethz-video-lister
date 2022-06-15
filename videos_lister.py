from logging import error
import requests
import json
from getpass import getpass
from optparse import OptionParser
import re
import sys


usage = "Usage: python3 %prog [options] URL"
parser = OptionParser(usage=usage)
parser.add_option("-r", "--resolution", dest="res", default=1080, type=int,help="list video files with height RES [default: %default]", metavar="RES")
parser.add_option("-f", "--file", dest="list_filename", help="write list to FILE [default: videolinks_{COURSE_TITLE}_{RES}p.txt]", metavar="FILE")

options, args = parser.parse_args()
options = vars(options)

if len(args)<1:
    parser.error("Please specify the url.")


h = options["res"]


re_base = re.match(r"https?://video.ethz.ch/lectures/d-\w{3,6}/\d{4}/(spring|autumn)/\d{3}-\d{4}-\d{2}L",args[0])

if re_base is None:
    sys.exit("Invalid url.")

base_url = re_base.group(0)

referer_url = f"{base_url}.html"

headers = {
    "Host": "video.ethz.ch",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:101.0) Gecko/20100101 Firefox/101.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": referer_url,
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

last = f"{base_url}.series-metadata.json"

req_last = requests.get(last, headers = headers)
last_json = json.loads(req_last.text)
episodes = last_json["episodes"][::-1]
list_filename = options["list_filename"] if options["list_filename"] else f"videolinks_{last_json['title'].replace(' ','_')}_{h}p.txt"


auth_cookies = None

if last_json["protection"] != "NONE":
    username = input("Username: ")
    password = getpass("Password: ")

    if last_json["protection"] == "PWD":
        login_url: str = f"{base_url}.series-login.json"
        data = {"_charset_": "utf-8", "username": username,
            "password": password}

        auth_headers = {
            "Host": "video.ethz.ch",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:101.0) Gecko/20100101 Firefox/101.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": "41",
            "Origin": "https://video.ethz.ch",
            "Connection": "keep-alive",
            "Referer": referer_url,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        auth_req = requests.post(login_url, headers=auth_headers, data=data)


        try:
            success = json.loads(auth_req.text)["success"]
        except json.decoder.JSONDecodeError:
            success = False
        
    elif last_json["protection"]=="ETH":
        login_url: str = f"{base_url}/j_security_check"

        data = {"_charset_": "utf-8", "j_username": username,
            "j_password": password, "j_validate": "true"}

        auth_headers = {
            "Host": "video.ethz.ch",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:101.0) Gecko/20100101 Firefox/101.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/x-www-form-urlencoded",
            "CSRF-Token": "undefined",
            "Content-Length": "57",
            "Origin": "https://video.ethz.ch",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": referer_url,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        auth_req = requests.post(login_url, headers=auth_headers, data=data)
        success = not "invalid_login" in auth_req.text

    else:
        sys.exit("Unknown authentication method.")

    if not success:
        sys.exit("Unable to login. Check your username and password.")

    print("Successfully logged in.")

    auth_cookies = auth_req.cookies

with open(list_filename, "w") as f:
    for episode in episodes:
        data_url = f"{base_url}/{episode['id']}.series-metadata.json"
        req = requests.get(data_url, headers=headers, cookies=auth_cookies)
        presentations = json.loads(req.text)["selectedEpisode"]["media"]["presentations"]
        for pres in presentations:
            if pres["height"] == h:
                f.write(f"{pres['url']}\n")

print(f"List saved in {list_filename}")

