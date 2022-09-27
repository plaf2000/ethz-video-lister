import os
import requests
from requests import cookies
import json
from getpass import getpass
from optparse import OptionParser
import re
import sys

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

class Courses:
    def __init__(self, fname):
        """

        """
        self.fname = fname
        if os.path.isfile(fname):
            with open(fname, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {}
    def add(self, raw_url: str):
        videos = Videos(raw_url)
        if not videos.login():
            sys.exit()
        data = {}
        data["protection"] = videos.protection
        data["name"] = videos.last["title"]
        data["username"] = None
        data["password"] = None
        if videos.protection == "ETH":
            data["username"] = videos.username
        elif videos.protection == "PWD":
            data["username"] = videos.username
            data["password"] = videos.password
        data["api_data"] = videos.json_data()
        data["presentations"] = videos.get_presentations()

        self.data.setdefault(raw_url, data)

        with open(self.fname, "w") as f:
            f.write(json.dumps(self.data))

    def delete(self, raw_url):
        if raw_url in self.data:
            del self.data[raw_url]
            with open(self.fname, "w") as f:
                f.write(json.dumps(self.data))
            return True
        return False
        
    def update(self,raw_url):
        self.eth_password = None
        old_data = self.data[raw_url]
        videos = Videos(raw_url)
        username = None if old_data["username"] is None else lambda: old_data["username"]
    
        if self.eth_password is not None and old_data["protection"] == "ETH":
            password = lambda _: self.eth_password
        else:
            password = None if old_data["password"] is None else lambda _: old_data["password"]
        
        videos.login(username, password)

        if self.eth_password is None and old_data["protection"] == "ETH":
            self.eth_password = videos.password
    
        
        self.data[raw_url]["api_data"] = videos.json_data()
        self.data[raw_url]["presentations"] = videos.get_presentations()


        with open(self.fname, "w") as f:
            f.write(json.dumps(self.data))

    def names_url(self,):
        courses = {}
        for url, data in self.data.items():
            courses[data["name"]] = url
        return courses

    def play_all(self, raw_url, player: str = "mpv", h=1080, revert_order=False):      
        if player=="mpv" or player=="vlc":
            self.update(raw_url)
            urls = []
            for pres in self.data[raw_url]["presentations"]:
                for pres_res in pres:
                    if pres_res["height"] == h:
                        urls.append(pres_res['url'])
            if revert_order:
                urls = urls[::-1]
            os.system(f"{player} {' '.join(urls)}")
        




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

        self.username = None
        self.password = None

    
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

    def get_presentations(self):
        presentations = []
        for episode in self.episodes:
            presentations.append(self.json_data(episode["id"])["selectedEpisode"]["media"]["presentations"])
        return presentations


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

        self.protection = self.last["protection"]

        if self.protection == "PWD":
            self.username = username()
            self.password = password(self.username)
            login_url: str = f"{self.base_url}.series-login.json"
            data = {"_charset_": "utf-8", "username": self.username,
                "password": self.password}

            

            auth_req = requests.post(login_url, headers=auth_headers, data=data)


            try:
                success = json.loads(auth_req.text)["success"]
            except json.decoder.JSONDecodeError:
                raise InvalidAuth()
            
        elif self.protection =="ETH":
            self.username = username()
            self.password = password(self.username)

            login_url: str = f"{self.base_url}/j_security_check"

            data = {"_charset_": "utf-8", "j_username": self.username,
                "j_password": self.password, "j_validate": "true"}

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


    def login(self, username = None, password = None):
        """
            Open a login form on the shell.

            Returns
            -------
            `True` on success, else keep asking for username and password (unless authentication method is unknown).
        """
        if self.is_open():
            print("Open-access videos. No need to login.")
        else:
            if username is None:
                username = lambda: input("Username: ")
            if password is None:
                password = lambda uname: getpass(f"Password for {uname}: ")
            try:
                self.set_auth_cookies(username,password)
            except UnknownAuthMethod as e:
                print(e)
                return False
            except InvalidAuth as e:
                print(e)
                return self.login(username, password)
            print("Successfully logged in.")
        return True



    

if __name__ == "__main__":
    usage = "Usage: python3 %prog [actions] [options]\n Possible actions are:\n\t add [URL]\n\t delete\n\t remove (delete alias)\n\t play"
    
    parser = OptionParser(usage=usage)
    parser.add_option("-r", "--resolution", dest="res", default=1080, type=int,help="list video files with height RES [default: %default]", metavar="RES")
    parser.add_option("-f", "--file", dest="courses_file", default=os.path.join(os.path.dirname(os.path.realpath(__file__)),"courses.json"), help="write data to FILE [default: %default]", metavar="FILE")
    parser.add_option("-p", "--player", dest="player", default="mpv", help="play with vlc or mpv [default: %default]", metavar="PLAYER")
    parser.add_option("-o", action="store_true", dest="revert_order",help="set the flag if you want to see videos in antichronological order")
    parser.set_defaults(revert_order=False)

    options, args = parser.parse_args()
    options = vars(options)




    if len(args)<1:
        parser.error("Please specify the action.")

    action = args[0]

    courses = Courses(options["courses_file"])

    def get_url_from_list():
        cnames = courses.names_url()
        i=1
        names_list = []
        for name in cnames:
            print(f"{i}) {name}")
            names_list.append(name)
            i+=1
            
        def get_num(msg):
            try:
                return int(input(msg))
            except ValueError:
                return get_num("Please enter a number: ")

        sel_i = get_num("Select a course by typing the corresponding number: ")
        while sel_i not in range(1,len(names_list)+1):
            sel_i = get_num("Select number in the correct range: ")
        
        return cnames[names_list[sel_i-1]]


    if action=="add":
        if len(args)<2:
            parser.error("Please provide an url.")
        else:
            try:
                courses.add(raw_url=args[1])
            except InvalidUrl as e:
                sys.exit(e)
        
    if action=="delete" or action=="remove":
        if not courses.delete(raw_url=get_url_from_list()):
            print("Course url was not found in local data.")
    
    if action == "play":
        h = options["res"]
        player = options["player"]
        courses.play_all(get_url_from_list(), player=player, h=h, revert_order=options["revert_order"])
    

 
            


