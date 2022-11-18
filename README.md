# Union Channel 
## What's it?

<img src="./images/telegram_feed.png" alt="architecture" align="center" width="700px"/>

This is a simple program that will aggregate all your channels into one, as well as filter ads and duplicates in them. 
Deduplication works based on media, text, and text format. Duplicated media is enough to be rejected even with a new text.

## How it works?

The program through your account goes to all the channels that you have added to the `channels.json` and sends them to 
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
1. Per-channel content recommender
   1. What content
      1. Just started. Do you like to follow [defaults]?
      2. Content from subscriptions
         1. when added a subscription: would you also like to subscribe to [channel similar to the added]
      3. New content non-following channels
      4. Channel recommendation itself (not content from it)? [Vlad](https://github.com/sawyre)'s idea). PageRank?
   2. Features/approaches
      1. RL for recommender
      2. content type (polls, gifs, etc)
2. Spam detection
      1. fix Russian spam-filter bypass #промо - generate automatically combinations
      2. ...читать продолжение… - generate automatically combinations
      3. user is able to add/delete this him/herself
      4. should be extendable to rexeps
   3. Per-channel ML trained on special spam-related reactions (this may be incorporated into recommender itself)
      1. count vectorizer to start with?
      2. Average URL Number per Message
      3. Unique URL Number
      4. domain
      5. add feedback loop from reactions in the chat (and some time after (from user's acceptance) delete the posts 
      marked as spam\uninteresting)
3. Examples of usage
   1. Gif with already working bot overview
      1. Scenario:
         1. user joins
         2. user creates a public channel
         3. user adds the bot to a newly created channel
         4. user goes to bot and adds a couple of subscriptions to a source channel
         5. bot sends content to the user's channel
         6. user checks new content and reacts
   2. Gif with using the commands
4. Bot functionality
    1. Forward to private channels
    2. add deletion from channel
    3. add dynamic fetching of the handlers
    4. Automatically send each user a notification with details when a new version of the code is merged to master
    5. make difference between help description and actual long explanation/return from the command
    6. when you start resolving the list of commands after the bot was off for some time, the commands are read backwards
for some reason
    7. resolve dst_ch reading another dst_ch. infinite forwarding btw dst channels
    8. /add_to_channel to be used from the channel itself with only one argument of src_ch. Make admin check
    9. send /help without a link to me
5. Deployment
   1. switch to a database
   2. database will contain user's preferences, subscription lists
   3. dev env will have only developers' channels to be checked for some time
6. Statistics 
   1. originality of content produced
      1. find real origins of forwarded forwarded...
      2. add counters to them 
   2. Number of src channels processed
   3. Posts forwarded 
   4. Timing, delays, potential scaling, bottlenecks
7. Add liked memes from profunctor
8. For ML-based spam detection and content recommendations: only admin's reactions or the whole channel's reactions
are used? user's decision per channel?
9. Update filtering rules to a list (mb dict with some level of severity)
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
12. If you are going to read several messages and the last one is a part of a group, the group has to be finished
13. In debug mode, show what kind of post was forwarded (what media inside)
14. trace channel name changes (is it possible? what API says)
15. clean `https://t.me/profunctor_io`
16. create a func for deleting messages via bot
17. send some filtered digest to user like "5 msg from this channel were filtered due to this and this filter. you can
still find this content via this link"
18. comments to the forwarded forwarded messages are sent after the actual message 
19. when forwarding, show the time of the original post (using API or just adding "orig time: ..." to the top)

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