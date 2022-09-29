import json
from typing import List

from telethon.tl.patched import Message
from telethon.tl.tlobject import TLObject
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage

import logging
logger = logging.getLogger(__name__)


def OpenJson(name):
    with open('data/%s.json' % name, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    return data


def SaveJson(name, data):
    with open('data/%s.json' % name, 'w') as f:
        json.dump(data, f)


# def check_copypaste(msg1, msg2, ch1='ch1', ch2='ch2'):
#     # TODO: check. doesn't work if the post is only an image
#     if msg1.message == msg2.message and msg1.entities == msg2.entities and msg1.media == msg2.media:
#         print('Found a duplicate')
#         print('msg1.message\n', msg1.message[:15], '...', msg1.message[-15:])
#         print('msg2.message\n', msg2.message[:15], '...', msg2.message[-15:])
#         print('msg1.entities\n', msg1.entities)
#         print('msg2.entities\n', msg2.entities)
#         print('msg1.media\n', msg1.media)
#         print('msg2.media\n', msg2.media)
#         if msg1.date > msg2.date:
#             print(f"Message '{msg1.message[:15]}...' was published by '{ch2}' before '{ch1}'")
#         else:
#             print(f"Message '{msg1.message[:20]}...' was published by '{ch1}' before '{ch2}'")
#         return True
#     else:
#         return False


def media_is_duplicated(m1, m2):
    if m1 is None and m2 is None:
        return True

    if type(m1) is not type(m2):
        return False

    if isinstance(m1, MessageMediaDocument):
        d1 = m1.document.to_dict()
        d2 = m2.document.to_dict()
    elif isinstance(m1, MessageMediaPhoto):
        d1 = m1.photo.to_dict()
        d2 = m2.photo.to_dict()
    elif isinstance(m1, MessageMediaWebPage):
        d1 = m1.webpage.to_dict()
        d2 = m2.webpage.to_dict()

    # file reference is different. https://core.telegram.org/api/file_reference
    d1.pop('file_reference', None)
    d2.pop('file_reference', None)
    # drop date as well?
    if d1 == d2:
        return True
    # else:
    #     logger.error(f'm1 type {type(m1)} or m2 type {type(m2)} is not TLObject')

    return False


def check_copypaste(msg1: Message, msg2: Message):
    is_copypaste = False

    if msg1.media is None:
        if msg2.media is None:
            if msg1.message == msg2.message and msg1.entities == msg2.entities:  # may be empty and None respectively
                is_copypaste = True
    else:
        if msg2.media is not None:
            # if both media are presented, it's enough to judge regardless of text
            is_copypaste = media_is_duplicated(msg1.media, msg2.media)

    if is_copypaste:
        print('Found a duplicate')
        print('msg1.message\n', msg1.message[:15], '...', msg1.message[-15:])
        print('msg2.message\n', msg2.message[:15], '...', msg2.message[-15:])
        print('msg1.entities\n', msg1.entities)
        print('msg2.entities\n', msg2.entities)
        print('msg1.media\n', msg1.media)
        print('msg2.media\n', msg2.media)

    return is_copypaste


def is_sponsored(msg: Message, rules_list: List[str]):
    """
    Checks if the message contains content to filter. If fails, returns the message as is.
    Each rules is compared in lowercase against the message
    :param msg:
    :param rules_list:
    :return:
    """
    try:
        for phrase in rules_list:
            if msg.message.lower().find(phrase.lower()) != -1:
                # logger.info(f"Message id {msg.id} is filtered according to the rule: {phrase}")
                logger.info(f"Message id {msg.id} is filtered according to the rule: {phrase}")
                return True
        return False
    except:
        logger.error(f"Failed to check the message {msg} against the phrase {phrase}")
        return False


def open_rules_file():
    """
    Opens file with rules for advertisements and returns a list with rules to apply
    :return:
    """
    ads = OpenJson(name="ads")
    ads_list = list()
    for ad in ads:
        ads_list.append(ad)  # each term may have it's priority. Now it's 0 as a placeholder
    return ads_list


def check_msg_list_for_adds(msg_list: List):
    checkrules_list = open_rules_file()

    if checkrules_list is None:
        logger.debug("There are no advertising\\filtering rules to check")
        return msg_list

    messages_checked_list = list()
    for msg in msg_list:
        if not is_sponsored(msg, checkrules_list):
            messages_checked_list.append(msg)
    return messages_checked_list


def OpenUpdateTime():
    return OpenJson(name="channels")


def SaveUpdateTime(key, LastMsg_id):
    channels = OpenJson(name="channels")
    channels[key] = LastMsg_id - 1  # why one last message is preserved
    SaveJson(name="channels", data=channels)


def SaveNewTime(channels):
    # print("SAVING: " + str(channels))
    SaveJson(name="channels", data=channels)


def check_channel_correctness(channel):
    """
    Checks the correctness of the channel name

    :param channel:
    :return:
    """
    channel = channel.replace("@", "https://t.me/")
    if channel.find("https://t.me/") == -1:
        channel = channel.replace("t.me/", "https://t.me/")
    if channel.find("https://t.me/") == -1:
        return "error"
    else:
        return channel