# xwini minibot
A bot for listing xwing miniatures
Based off the hearthscan-bot - https://github.com/d-schmidt/hearthscan-bot
Card data from Geordanrs xwing squad builder project - https://github.com/geordanr/xwing

## Requirements
- tested with Python 3.4+
- libraries used: `requests`, `praw`, `lxml`
- [Reddit API](https://www.reddit.com/prefs/apps/) id, secret and refresh token

## Running the bot
**Make sure the online test is successful!**  
I use the `start.sh` on my PI to run in background.  
If you want to start it without, no parameters are required (`python3 hearthscan-bot.py`).  
The script pipes startup errors to `std.txt` and `err.txt`. The bot logs to `bot.log` once it is running.

Delete the `lockfile.lock` to stop the bot gracefully.

## License
All code contained here is licensed by [MIT](https://github.com/d-schmidt/hearthscan-bot/blob/master/LICENSE).
