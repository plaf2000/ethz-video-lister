import requests
from requests import cookies
import json
from getpass import getpass
from optparse import OptionParser
import re
import sys

from sympy import true

class InvalidUrl(ValueError):
    def __init__(self,url):
        super().__init__(f"The url {url} doesn't match the expected pattern.")

class UnableToLogin(RuntimeError):
    def __init__(self,msg: str):
        super().__init__(f"Unable to login. {msg}")

class InvalidAuth(UnableToLogin):
    def __init__(self):
        super().__init__("Invalid values. Check your username and password.")
    
class UnknownAuthMethod(UnableToLogin):
    def __init__(self):
        super().__init__("Unknown authentication method.")

class Videos:
    def __init__(self, raw_url: str):
        """
            Parameters
            ----------
             - `raw_url`: url matching following pattern: `https?://video.ethz.ch/lectures/d-\w{3,6}/\d{4}/(spring|autumn)/\d{3}-\d{4}-\d{2}L`
        """

        re_base = re.match(r"https?://video.ethz.ch/lectures/d-\w{3,6}/\d{4}/(spring|autumn)/\d{3}-\d{4}-\d{2}L",raw_url)
        if re_base is None:
            raise InvalidUrl(raw_url)
        self.base_url=re_base.group(0)
        self.referer_url = f"{self.base_url}.html"
        self.base_header = {
            "Host": "video.ethz.ch",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:101.0) Gecko/20100101 Firefox/101.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": self.referer_url,
            "Connection": "keep-alive",
            "Sec-Fetch-Site": "same-origin",

        }
        self.videos_header =  self.base_header | {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
        }
        self.auth_cookies: cookies.RequestsCookieJar | None = None

        self.last = self.json_data()
        self.episodes  = self.last["episodes"][::-1]

    
    def json_data(self, episode_id: str | None = None):
        """
            Parameters
            ----------
             - `episode_id`: id of the episode you want to get the data from.
        """

        episode = f"/{episode_id}" if episode_id is not None else ""
        data_url = f"{self.base_url}{episode}.series-metadata.json"
        req = requests.get(data_url, headers=self.videos_header, cookies=self.auth_cookies)
        return json.loads(req.text)


    def is_open(self):
        """            
            Returns
            -------
            True if the videos are open and there's no need to be logged in.
        """
        return self.last["protection"] == "NONE"

    def set_auth_cookies(self, username, password) -> cookies.RequestsCookieJar | None:
        """
            Parameters
            ----------
             - `username`: function which returns the username
             - `password`: function which returns the password
            
            Returns
            -------
            The authorisation's cookies.
        """

        if self.is_open():
            return self.auth_cookies

        auth_headers = self.base_header | {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": "41",
            "Origin": "https://video.ethz.ch",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
        }

        if self.last["protection"] == "PWD":
            login_url: str = f"{self.base_url}.series-login.json"
            data = {"_charset_": "utf-8", "username": username(),
                "password": password()}

            auth_req = requests.post(login_url, headers=auth_headers, data=data)


            try:
                success = json.loads(auth_req.text)["success"]
            except json.decoder.JSONDecodeError:
                raise InvalidAuth()
            
        elif self.last["protection"]=="ETH":
            login_url: str = f"{self.base_url}/j_security_check"

            data = {"_charset_": "utf-8", "j_username": username(),
                "j_password": password(), "j_validate": "true"}

            auth_headers |= {
                "CSRF-Token": "undefined",
                "Content-Length": "57",
                "DNT": "1",
            }

            auth_req = requests.post(login_url, headers=auth_headers, data=data)
            success = not "invalid_login" in auth_req.text
        else:
            raise UnknownAuthMethod()            

        if not success:
            raise InvalidAuth()
        self.auth_cookies =  auth_req.cookies
        return self.auth_cookies


    def login(self):
        """
            Open a login form on the shell.

            Returns
            -------
            `True` on success, else keep asking for username and password (unless authentication method is unknown).
        """
        if self.is_open():
            print("Open-access videos. No need to login.")
        else:
            username = lambda: input("Username: ")
            password = lambda: getpass("Password: ")
            try:
                self.set_auth_cookies(username,password)
            except UnknownAuthMethod as e:
                print(e)
                return False
            except InvalidAuth as e:
                print(e)
                return self.login()
            print("Successfully logged in.")
        return True
    

if __name__ == "__main__":
    usage = "Usage: python3 %prog [options] URL"
    parser = OptionParser(usage=usage)
    parser.add_option("-r", "--resolution", dest="res", default=1080, type=int,help="list video files with height RES [default: %default]", metavar="RES")
    parser.add_option("-f", "--file", dest="list_filename", help="write list to FILE [default: videolinks_{COURSE_TITLE}_{RES}p.txt]", metavar="FILE")

    options, args = parser.parse_args()
    options = vars(options)

    if len(args)<1:
        parser.error("Please specify the url.")

    h = options["res"]

    try:
        videos = Videos(args[0])
    except InvalidUrl as e:
        sys.exit(e)

    list_filename = options["list_filename"] if options["list_filename"] else "videolinks_{}_{}p.txt".format(re.sub(r'\W','',re.sub(r'-| ','_',videos.last['title'])), h)


    if not videos.login():
        sys.exit()

    with open(list_filename, "w") as f:
        for episode in videos.episodes:
            presentations = videos.json_data(episode["id"])["selectedEpisode"]["media"]["presentations"]
            for pres in presentations:
                if pres["height"] == h:
                    f.write(f"{pres['url']}\n")

    print(f"List saved in {list_filename}")

