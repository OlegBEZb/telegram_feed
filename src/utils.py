import json
import time
from copy import deepcopy

from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest, CheckChatInviteRequest, ImportChatInviteRequest

from telethon.tl.patched import Message
from telethon.tl.types import PeerChannel, MessageFwdHeader

import logging
logger = logging.getLogger(__name__)

from src import config

from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def OpenJson(name):
    import os
    root = get_project_root()
    with open(os.path.join(root, f"src/data/{name}.json"), 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    return data


def SaveJson(name, data):
    with open('data/%s.json' % name, 'w') as f:
        json.dump(data, f)


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


def get_reactions(msg: Message):
    if msg.reactions is not None:
        reactions = msg.reactions.results
        d = {}
        for reaction in reactions:
            d[reaction.reaction] = reaction.count
        return d


def chat_id2name(client: TelegramClient, chat_id):
    entity = client.get_input_entity(PeerChannel(chat_id))
    chat_full = client(GetFullChannelRequest(entity))
    if hasattr(chat_full, 'chats') and len(chat_full.chats) > 0:
        chat_title = chat_full.chats[0].title
        return chat_title


# TODO: extension to the end of the group
def get_history(client: TelegramClient, **get_history_request_kwargs):
    """
    For reference: https://core.telegram.org/api/offsets.

    :param client:
    :param peer: Target peer
    :param offset_id: Only return messages starting from the specified message ID
    :param offset_date: Only return messages sent before the specified date
    :param add_offset: Number of list elements to be skipped, negative values are also accepted.
    :param limit: Number of results to return. A limit on the number of objects to be returned, typically
    between 1 and 100. When 0 is provided the limit will often default to an intermediate value like ~20.
    :param max_id: If a positive value was transferred, the method will return only messages with IDs less than
    max_id
    :param min_id: 	If a positive value was transferred, the method will return only messages with IDs more than
    min_id
    :param hash: Result hash

    :returns messages.Messages: Instance of either Messages, MessagesSlice, ChannelMessages, MessagesNotModified.
    """
    get_history_default = {'offset_id': 0, 'offset_date': 0,
                           'add_offset': 0, 'limit': 1,
                           'max_id': 0, 'min_id': 0,
                           'hash': 0}  # min and max ids 0 or -1?
    # the dict on the right takes precedence
    get_history_request_kwargs = get_history_default | get_history_request_kwargs

    if get_history_request_kwargs['limit'] > 100:
        print('downloading by chunks')
        # messages = get_long_history(client, peer, min_id, limit)
        partial_kwargs = deepcopy(get_history_request_kwargs)
        moving_max_id = get_history_request_kwargs['max_id']  # starting from the original ceiling
        limit = get_history_request_kwargs['limit']
        messages_total = None
        while True:
            partial_kwargs['offset_id'] = moving_max_id
            partial_kwargs['limit'] = min(100, limit)

            messages = client(GetHistoryRequest(**partial_kwargs))
            if messages_total is None:
                messages_total = messages
            else:
                # messages and chats users to flat
                messages_total.messages += messages.messages
                messages_total.chats += [c for c in messages.chats if c not in messages_total.chats]
                messages_total.users += [c for c in messages.users if c not in messages_total.users]
            dumped_num = len(messages.messages)
            print('dumped', dumped_num, 'more messages')
            print('total', len(messages_total.messages))

            limit -= dumped_num
            if dumped_num < 100 or limit == 0:
                break
            moving_max_id = min(msg.id for msg in messages.messages)

            time.sleep(1)
        messages = messages_total
    else:
        messages = client(GetHistoryRequest(**get_history_request_kwargs))
    return messages


def get_source_channel_name_for_message(client: TelegramClient, msg: Message):
    if isinstance(msg.fwd_from, MessageFwdHeader):
        orig_name = chat_id2name(client, msg.fwd_from.from_id.channel_id)
        orig_date = msg.fwd_from.date
        fwd_to_name = chat_id2name(client, msg.chat_id)
        fwd_date = msg.date
    else:
        orig_name = chat_id2name(client, msg.chat_id)
        orig_date = msg.date
        fwd_to_name, fwd_date = None, None

    return orig_name, orig_date, fwd_to_name, fwd_date


def CheckCorrectlyPrivateLink(client: TelegramClient, req):
    try:
        client(CheckChatInviteRequest(hash=req))
        return True
    except:
        return False


def Subs2PrivateChat(client: TelegramClient, req):
    try:
        updates = client(ImportChatInviteRequest(req))
        client.edit_folder(updates.chats, 1)  # 1 is archived 0 unarchived
    except:
        print("already subs")


def start_client():
    api_id = config.api_id
    api_hash = config.api_hash

    isNotConnected = True
    connection_attempts = 1
    while isNotConnected:
        try:
            logger.debug(f"Connection attempt: {connection_attempts}")
            client = TelegramClient('telefeed_client', api_id, api_hash)
            client.start()
            logger.debug('TelegramClient is started\n')
            isNotConnected = False
        except Exception as e:
            connection_attempts += 1
            logger.error(str(e))
            time.sleep(30)

    return client