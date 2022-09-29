# Union Channel 
## What's it?

This is a simple program that will combine all your channels into one, as well as filter ads and duplicates in them. 
Deduplication works based on media, text, and text format. Duplicated media is enough to be rejected even with a new text.

## How it works?

The program through your account goes to all the channels that you have added to the `channels.json` and sends them to your personal (or not) channel.
Subscribe to the channels in the telegrams is not required (based on the original realisation).

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

+ On first start you must enter phone-number and password from telegram-account. Telethon requried.
## Some bot commands

    /add - Add channel
    /del - Delete channel
    /channels - Channels List
    /addrule - Add rule
    /delrule - Delete rule
    /setads - Enable/Disable AdBlock
    /rules - List of AdBlock rules


# TODO
1. Calculate statistics for originality of content produced
   1. find real origins of forwarded forwarded...
   2. add counters to them 
3. Deduplication of subscriptions
4. Add liked memes from profunctor
5. Add reactions + spam report to be automatically used as a per-person feedback loop
   1. Add recommender system
6. Serve as bot which everyone can configure for personal needs and personal feed
7. Add more complex spam detector
   1. count vectorizer to start with?
   2. Average URL Number per Message
   3. Unique URL Number
   4. domain
   5. add feedback loop from my reactions in the chat (and then delete the posts)
8. Add dict with channel names from ids?
9. Update filtering rules to a list (mb dict with some level of severity)
10. Check forwarding from channels without subscription