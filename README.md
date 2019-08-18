# ytc_dl
Script to download comments off of YouTube videos without adding views. No API keys needed. Would be nice to implement this into youtube-dl.

This has been figured out by tracking the network requests sent to AJAX URLs when new comments are being loaded. These URLs can be found in Firefox -> inspect element -> network. The requests will be .json files and the page tokens and of course comments and replies are extracted. 

What the program does is first load the page, then load the comment section and doing so extract the comments amount and page token to load newest comments. Then the bot works through all comments and in separated, pooled (?) threads fetches the replies. Progress is displayed in a tqdm progress bar. All these comments along with their metadata, are stored in a dictionary. After all comments are fetched, the dictionary is stored in a .json file and a .html file is created to embed the comment section in your browser. 


