import os
import requests
import subprocess
from requests import cookies
import json
from getpass import getpass
from optparse import OptionParser
import re
import sys
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile

class InvalidUrl(ValueError):
    def __init__(self, url):
        super().__init__(f"The url {url} doesn't match the expected pattern.")


class UnableToLogin(RuntimeError):
    def __init__(self, msg: str):
        super().__init__(f"Unable to login. {msg}")


class InvalidAuth(UnableToLogin):
    def __init__(self):
        super().__init__("Invalid values. Check your username and password.")


class UnknownAuthMethod(UnableToLogin):
    def __init__(self):
        super().__init__("Unknown authentication method.")


class Courses:
    def __init__(self, fname, pfolder):
        """

        """
        self.fname = fname
        if os.path.isfile(fname):
            with open(fname, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {}
        self.playlists_folder = pfolder

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
        videos.set_presentations(data)

        self.data.setdefault(raw_url, data)
        self.save_data()

    def save_data(self):
        with open(self.fname, "w") as f:
            f.write(json.dumps(self.data))

    def delete(self, raw_url):
        if raw_url in self.data:
            del self.data[raw_url]
            self.save_data()
            return True
        return False

    def update(self, raw_url, force=False):
        self.eth_password = None
        old_data = self.data[raw_url]
        videos = Videos(raw_url)
        last_stored_dt = datetime.fromisoformat(
            old_data["api_data"]["episodes"][0]["createdAt"])
        last_updated_dt = datetime.fromisoformat(
            videos.episodes[-1]["createdAt"])
        if last_updated_dt == last_stored_dt and not force:
            return

        username = None if old_data["username"] is None else lambda: old_data["username"]

        if self.eth_password is not None and old_data["protection"] == "ETH":
            def password(_): return self.eth_password
        else:
            password = None if old_data["password"] is None else lambda _: old_data["password"]

        videos.login(username, password)

        if self.eth_password is None and old_data["protection"] == "ETH":
            self.eth_password = videos.password

        self.data[raw_url]["api_data"] = videos.json_data()
        videos.set_presentations(self.data[raw_url])

        self.save_data()

    def names_url(self,):
        courses = {}
        for url, data in self.data.items():
            courses[data["name"]] = url
        return courses

    def play_all(self, raw_url, player: str = "mpv", h=1080):
        if player == "mpv" or player == "vlc":
            self.update(raw_url)
            opts = [self.playlist_path(raw_url=raw_url)]

            if player=="mpv":
                opts.append("--save-position-on-quit")

            self.generate_M3U(raw_url=raw_url, h=h)
            
            proc = subprocess.Popen([player] + opts, stderr=subprocess.DEVNULL ,stdout=subprocess.DEVNULL)
            return proc
        
    def generate_M3U(self, raw_url, h):

        data_course = self.data[raw_url]
        episodes = data_course["api_data"]["episodes"][::-1]

        time_ptr = ""
        if "last_played" in data_course:
            time_ptr = f"#EXT-X-START: TIME-OFFSET={data_course['last_played']}"

        m3u = ""

        for episode in episodes:
            for pres_res in episode["media"]:
                if pres_res["height"] == h:
                    url = pres_res['url']
                    m3u+=f"#EXTINF:{episode['duration']},{data_course['name']} - {datetime.fromisoformat(episode['createdAt']).strftime('%c')}\n"
                    m3u+=f"{url}\n\n"

        m3u = f"#EXTM3U\n{time_ptr}\n#PLAYLIST:{data_course['name']}\n\n{m3u}"

        with open(self.playlist_path(raw_url=raw_url), "w") as fp:
            fp.write(m3u)
    
    def playlist_path(self, raw_url):
        l_id = re.search(r"\d{3}-\d{4}-\d{2}L", raw_url).group(0)
        return os.path.join(self.playlists_folder,f"{l_id}.m3u")



    def set_last_played(self, stoud: bytes, stderr: bytes, raw_url: str, player: str):
        out = stoud.decode("utf-8")
        err = stderr.decode("utf-8")
        if player=="mpv":
            urls = re.findall(r"Playing: (https?://.*)\n", out)
            acc_t = 0
            found = False
            for episode in self.data[raw_url]["api_data"]["episodes"][::-1]:
                for media in episode["media"]:
                    if media["url"] == urls[-1]:
                        found = True
                        break
                if found:
                    break
                acc_t += episode["duration"]
            h, m, s = re.findall(r"(\d{2}):(\d{2}):(\d{2}) /", err)[-1]
            h, m, s = int(h), int(m), int(s)
            ts_td = timedelta(hours=h,minutes=m, seconds=s)
            self.data[raw_url]["last_played"] = int(acc_t + ts_td.total_seconds())
            self.save_data()
            

class Videos:
    def __init__(self, raw_url: str):
        """
            Parameters
            ----------
             - `raw_url`: url matching following pattern: `https?://video.ethz.ch/lectures/d-\\w{3,6}/\\d{4}/(spring|autumn)/\\d{3}-\\d{4}-\\d{2}L`
        """

        re_base = re.match(
            r"https?://video.ethz.ch/lectures/d-\w{3,6}/\d{4}/(spring|autumn)/\d{3}-\d{4}-\d{2}L", raw_url)
        if re_base is None:
            raise InvalidUrl(raw_url)
        self.base_url = re_base.group(0)
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
        self.videos_header = self.base_header | {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
        }
        self.auth_cookies: cookies.RequestsCookieJar | None = None

        self.last = self.json_data()

        self.username = None
        self.password = None

    @property
    def episodes(self):
        return self.last["episodes"][::-1]

    def json_data(self, episode_id: str | None = None):
        """
            Parameters
            ----------
             - `episode_id`: id of the episode you want to get the data from.
        """

        episode = f"/{episode_id}" if episode_id is not None else ""
        data_url = f"{self.base_url}{episode}.series-metadata.json"
        req = requests.get(data_url, headers=self.videos_header,
                           cookies=self.auth_cookies)
        json_data = json.loads(req.text)
        return json_data

    def set_presentations(self, data):
        for episode in data["api_data"]["episodes"]:
            json_data = self.json_data(episode["id"])
            dur = json_data["selectedEpisode"]["duration"]
            time_match = re.search(r"(\d+)H", dur)
            h = 0 if not time_match else int(time_match.group(1))
            time_match = re.search(r"(\d+)M", dur)
            m = 0 if not time_match else int(time_match.group(1))
            time_match = re.search(r"(\d+\.?\d*)S", dur)
            s = 0 if not time_match else float(time_match.group(1))
            s_ = int(s)
            ms = int((s-s_) * 1e3)

            dur_time = timedelta(hours=h, minutes=m, seconds=s_, milliseconds=ms)
            episode["duration"] = dur_time.total_seconds()
            episode["media"] = json_data["selectedEpisode"]["media"]["presentations"]

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

            auth_req = requests.post(
                login_url, headers=auth_headers, data=data)

            try:
                success = json.loads(auth_req.text)["success"]
            except json.decoder.JSONDecodeError:
                raise InvalidAuth()

        elif self.protection == "ETH":
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

            auth_req = requests.post(
                login_url, headers=auth_headers, data=data)
            success = not "invalid_login" in auth_req.text
        else:
            raise UnknownAuthMethod()

        if not success:
            raise InvalidAuth()
        self.auth_cookies = auth_req.cookies
        return self.auth_cookies

    def login(self, username=None, password=None):
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
                def username(): return input("Username: ")
            if password is None:
                def password(uname): return getpass(f"Password for {uname}: ")
            try:
                self.set_auth_cookies(username, password)
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


    try:
        parser = OptionParser(usage=usage)
        parser.add_option("-r", "--resolution", dest="res", default=1080, type=int,
                        help="list video files with height RES [default: %default]", metavar="RES")
        parser.add_option("-f", "--file", dest="courses_file", default=os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "courses.json"), help="write data to FILE [default: %default]", metavar="FILE")
        parser.add_option("-l", "--playlists-folder", dest="playlists_folder", default=os.path.join(os.path.dirname(
            os.path.realpath(__file__)), "playlists"), help="write playlists in FOLDER [default: %default]", metavar="FOLDER")
        parser.add_option("-p", "--player", dest="player", default="mpv",
                        help="play with vlc or mpv [default: %default]", metavar="PLAYER")

        options, args = parser.parse_args()
        options = vars(options)

        if len(args) < 1:
            parser.error("Please specify the action.")

        action = args[0]

        courses = Courses(options["courses_file"], options["playlists_folder"])

        def get_url_from_list():
            cnames = courses.names_url()
            i = 1
            names_list = []
            for name in cnames:
                print(f"{i}) {name}")
                names_list.append(name)
                i += 1

            def get_num(msg):
                try:
                    return int(input(msg))
                except ValueError:
                    return get_num("Please enter a number: ")

            sel_i = get_num("Select a course by typing the corresponding number: ")
            while sel_i not in range(1, len(names_list)+1):
                sel_i = get_num("Select number in the correct range: ")

            return cnames[names_list[sel_i-1]]

        if action == "add":
            if len(args) < 2:
                parser.error("Please provide an url.")
            else:
                try:
                    courses.add(raw_url=args[1])
                except InvalidUrl as e:
                    print(e)
                    sys.exit()

        if action == "delete" or action == "remove":
            if not courses.delete(raw_url=get_url_from_list()):
                print("Course url was not found in local data.")

        if action == "play":
            h = options["res"]
            player = options["player"]
            course_url = get_url_from_list()
            proc=courses.play_all(course_url, player=player,
                            h=h)
            sys.exit()
            if proc:
                courses.set_last_played(proc.stdout, proc.stderr, course_url, player)
    except KeyboardInterrupt:
        print("\nBye!")
