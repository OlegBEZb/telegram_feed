# telefeed 
## What's it?

<img src="./images/telegram_feed.png" alt="architecture" align="center" width="700px"/>

This is a service that will aggregate all your channels into one, as well as filter ads and duplicates in them. 
Deduplication works based on media, text, and text format. Duplicated media is enough to be rejected even with a new text.

## How it works?

The program through your account goes to all the channels that you have added and sends them to 
your personal (or not) channel. Subscribe to the channels in the telegrams is not required (based on the original 
realisation).

>In the new version, you can subscribe to a private channel. All private channels require a subscription therefore you will be automatically subscribed to this channel. It will be immediately archived

## How to use?

+ Firstly, install all requirements with 
    >pip install -r requirements.txt
+ Go to my.telegram.org and create your own app (get your api_id and api_hash).
+ Create a channel where you want to see the news.
+ Create a bot with t.me/BotFather.
+ Now paste all data into `config.py`, like this:

      ###     Telegram-client side:   ###
      api_id = XXXX
      api_hash = "XXXXXXXXXXXXXXXXXXX"
      MyChannel = "XXXXXXXXXXXXXXXXXXXXXXXX" # link to your chat 
 
      ###          Bot-side:          ###
      bot_token = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
      admin_chat_id = None       
      channel_id = None

 Data like `admin_chat_id` and `channel_id` you can get with debug value ("None") and replace. Optional:

        admin_chat_id = 12345       
        channel_id = -1234567

+ On first start you must enter phone-number and password from telegram-account. Telethon required.
## Some bot commands

    /add - Add channel
    /del - Delete channel
    /channels - Channels List
    /addrule - Add rule
    /delrule - Delete rule
    /setads - Enable/Disable AdBlock
    /rules - List of AdBlock rules


# TODOs with descending priorities
1. Shared util for extracting usual fields from a message. Pass already extracted features to the recommender
   1. transactions
   2. download history with reactions
   3. recommender
2. Per-channel content recommender
   1. On what level to predict: message, group, sending time
   2. What content
      1. Just started. Do you like to follow [defaults]? Top 3 buttons
      2. Content from subscriptions
         1. when added a subscription: would you also like to subscribe to [channel similar to the added]
      3. New content non-following channels
      4. Channel recommendation itself (not content from it)? [Vlad](https://github.com/sawyre)'s idea). PageRank?
   3. Features/approaches
      1. RL for recommender
      2. content type (polls, gifs, etc)
      3. is subscribed to this channel
      4. reactions from the original channel as features for recommender
      5. is a group message
         1. this group has poll, images..
      6. target: 10 - like, -1 - unread for a long time, -5 - dislike, -10 - spam
      7. today already received num. Or incorporate the history somehow?
   4. Detect the desired amount of content per day/hour and do not recommend more (may affect the thresholds for recommender)
3. Filtering
   1. Spam detection
         1. Fit a per-user model based on spam reactions
         2. fix Russian spam-filter bypass #промо - generate automatically combinations or normalize all texts (forever or only for filtering purposes)
         3. ...читать продолжение… - generate automatically combinations
         4. user is able to add/delete this him/herself
         5. should be extendable to rexeps
         6. Filtering rules with some level of severity
         7. Per-channel ML trained on special spam-related reactions (this may be incorporated into recommender itself)
            1. count vectorizer to start with?
            2. Average URL Number per Message
            3. Unique URL Number
            4. domain
            5. add feedback loop from reactions in the chat (and some time after (from user's acceptance) delete the posts 
            marked as spam\uninteresting)
         8. Get filtering examples from another bots on github 
   2. Deduplication
      1. Check fuzzy match for long texts. May be leading in comparison to the status quo when duplicated image is enough
         1. Identical texts longer than 50 symbols are quite rare... Deduplicate them regardless of the images?
      2. Fuzzy deduplication of images 
         1. https://www.youtube.com/watch?v=f60K3njUpK4&ab_channel=ODSAIGlobal
         2. https://www.kaggle.com/code/franckepeixoto/phash-determine-whether-2-images-are-equal-or-not/notebook
            1. https://github.com/OlegBEZb/MemeMash/blob/main/find_similar_images.py
4. Examples of usage
   1. Gif with already working bot overview
      1. Scenario:
         1. user has 3 channels with tons of unread messages
         2. user joins
         3. user creates a public channel
         4. user adds the bot to a newly created channel
         5. user goes to bot and adds a couple of subscriptions to a source channel
         6. bot sends content to the user's channel
         7. user checks new content and reacts
   2. Gif with using the commands
5. Bot functionality
    4. Forward to private channels 
    5. Remove start from menu
    6. About to the channel about?
    7. Create a channel for user and leave it after making the user an admin https://tl.telethon.dev/methods/channels/create_channel.html
    8. add deletion from channel
    9. add dynamic fetching of the handlers
    10. Automatically send each user a notification with details when a new version of the code is merged to master
    11. when you start resolving the list of commands after the bot was off for some time, the commands are read backwards
for some reason
    12. resolve dst_ch reading another dst_ch. infinite forwarding btw dst channels
    13. /add_to_channel to be used from the channel config itself with only one argument of src_ch. Make admin check
    14. consider a link typed in the chat as a suggestion to add it as a source somewhere. Ask "which target channel to add to"
    15. consider adding reaction buttons
    16. add some func for conversations def conv(question, timeout) -> answer
6. Deployment
   1. switch to a database
   2. database will contain user's preferences, subscription lists
   3. dev env will have only developers' channels to be checked for some time
7. Statistics 
   1. originality of content produced by source channels (which original content they steal)
   2. "5 msg from this channel were filtered due to this and this filter. you can
still find this content via this link"
   3. Timing, delays, potential scaling, bottlenecks
   4. Number of users reactions + "don't forget to react to the content"
   5. who reads posts
8. Add liked memes from profunctor
9. For ML-based spam detection and content recommendations: only admin's reactions or the whole channel's reactions
are used? user's decision per channel?
10. deduplicate if the post covers the same news or the same model (within some period of time). 
Different opinions from different channels might be interesting but very similar content 
about the same news is definitely not
     1. text similarity?
     2. same references used (links, channels, named entities)
        1. if channel B refers to channel A in their post, the channel's B note may be added to the
        channel's A repost at the end as an opinion
     3. time of the post is more or less similar (within 24 hour or sth)
     4. What to do with that?
        1. First served policy
        2. Somehow aggregate opinions from different channels via updating the first post on this topic
        3. Take better?
        4. use new telegram's feature called topics
11. If server is not available, close the session
12. If you are going to fetch several messages and the last one is a part of a group, the group has to be finished _get_history_
13. In debug mode, show what kind of post was forwarded (what media inside)
14. clean `https://t.me/profunctor_io`
15. create a func for deleting messages via bot
16. comments to the forwarded forwarded messages are sent after the actual message 
17. when forwarding, show the time of the original post (using API or just adding "orig time: ..." to the top)
18. Users list has to be updated according to the users who actually already stopped the bot or didn't add any channel
19. If something failed, do not mark as unread
20. Tests:
    1. channel renaming
    2. channel deletion
21. Add decorators
    1. Bot used only in a personal chat
    ```if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    ```
    2. Only owner can perform this action
    3. {await get_display_name(bot_client, int(sender_id))} ({sender_id}) called /command


# Static code analysis
In this repo I use [pre-commit framework](https://pre-commit.com/) to organise code analysis. This framework does all 
the arrangements with hooks for you having the .pre-commit-config.yaml file. This file is configured once and stored 
in the repository as a usual file. Every change will be automatically taken into account.

Only two simple manual steps are required:
1. Install the package via `pip install pre-commit` or may be just included to the requirements (done)
2. Initialize the framework `pre-commit install`. May be added to the setup script (not done)

If you want to check the hook without an event, run `pre-commit run --all-files`.

## Configuration files
Files (located in the root of the repo) involved into code analysis:
* .pre-commit-config.yaml - pre-commit hook description aka 'what to do when commited'
* .prospector.yml - Prospector configuration
* .pylintrc - detailed Pylint configuration used in Prospector
* .bandit.yml - detailed Bandit configuration used in Prospector
These files may be easily copied to another repository and configured based on the new requirements.

# Developing notes
1. It was a news for me that programming a telegram bot is not the only thing you can program for Telegram. Telegram
offers [two kinds of APIs for developers](https://core.telegram.org/api): "the Bot API allows you to easily create 
programs that use Telegram messages for an interface. The Telegram API and TDLib allow you to build your own customized 
Telegram clients.". In other words, you can interact in almost any possible way with Telegram via API and develop any 
kind of application based on this API. Bots are just a popular use-case covered with various handy libraries.
2. [This page lists some libraries and frameworks developed by the Telegram community](https://core.telegram.org/bots/samples). 
Personally, I feel myself comfortable with [Python ones](https://core.telegram.org/bots/samples#python). I have briefly
estimated most of these libraries\frameworks and here are my thoughts:
   1. [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - the most popular and the most
frequently updated. The interface doesn't look friendly
   2. [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) - the second most-popular library. The repo is 
also alive. The API looks similar to [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) 
but in my opinion is friendlier. I started with it but realised that the bot API is limited and you have to use your own
account for check channel history, for example.
   3. [Telethon](https://github.com/LonamiWebs/Telethon) - too difficult for me. I found a snipped and used in another 
[project of mine](https://github.com/OlegBEZb/telebot/blob/main/interactive_telegram_client.py). At first, I didn't want 
to use it because I completely don't know asyncio. But because of the reason mentioned in the previous point (plus due 
to [this concept](https://github.com/LonamiWebs/Telethon/blob/v1/readthedocs/concepts/botapi-vs-mtproto.rst)), 
I chose Telethon finally.
   4. [telepot](https://github.com/nickoala/telepot) - great but abandoned. I tried it but the library is very outdated 
with respect to the API used and requires manual patches.
([example](https://stackoverflow.com/questions/66796130/python-bot-telepot-error-raise-keyerrorno-suggested-keys-s-in-s-strkey)).
3. Great snippets were found in the following repos:
   1. https://github.com/Lonami/TelethonianBotExt/blob/master/main.py
   2. https://github.com/leomedo/pyLeader
4. Found already existing solutions with the same name :( 
   1. https://telefeed.readthedocs.io/
   2. https://telegrambotting.com/tg_feed
   3. https://github.com/hyzyla/telefeed
5. Great intro to asyncio https://www.youtube.com/watch?v=Xbl7XjFYsN4&t=1s&ab_channel=EdgeDB. But I still do not 
understand it
6. Tradeoff between .session and manual cache. Telethon promises to store some cache in .session file. This file has to
be removed before using different credentials, for example, IDs and hashes. If the identity is not in the .session file,
then Telethon makes a request. Unfortunately, request is not performed for a pure ID. I see some reason for that like
"it's quite difficult to obtain this ID without an API call. Therefore, this value should be already in the .session 
file and there is no need for making a request. For this purpose I have implemented local cache for ID, name, and link 
triples which are refreshed from time to time".