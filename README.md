# ETHZ Video lister

It allows you to login to the ethz video portal (depending on the authorisation method) and lists all links to mp4 files in a txt file. Useful for creating playlists in VLC/MPV.

## Usage

```
Usage: python3 videos_lister.py [actions] [options]
 Possible actions are:
	 add [URL]
	 delete
	 remove (delete alias)
	 play

Options:
  -h, --help            show this help message and exit
  -r RES, --resolution=RES
                        list video files with height RES [default: 1080]
  -f FILE, --file=FILE  write data to FILE [default: /home/plaf2000/Documents/
                        Scuola/ETH/videos_lister/courses.json]
  -p PLAYER, --player=PLAYER
                        play with vlc or mpv [default: mpv]
  -o                    set the flag if you want to see videos in
                        antichronological order
```
Example for an URL to provide: `https://video.ethz.ch/lectures/d-infk/2022/spring/252-0058-00L.html`. Possible resolutions are usually 1080, 720 and 360p.
