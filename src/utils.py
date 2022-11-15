import json
import os
import time
from copy import deepcopy
from pathlib import Path

from telethon import TelegramClient, types, utils as tutils
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest, CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.patched import Message
from telethon.tl.types import MessageFwdHeader

from src import config

import logging
logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def open_json(name):
    root = get_project_root()
    with open(os.path.join(root, f"src/data/{name}.json"), 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    return data


def check_channel_correctness(channel: str) -> str:
    """
    Checks the correctness of the channel name

    :param channel:
    :return:
    """
    channel = channel.replace("@", "https://t.me/")
    if channel.find("https://t.me/") == -1:
        channel = channel.replace("t.me/", "https://t.me/")
    if channel.find("https://t.me/") == -1:
        # return "error"
        raise ValueError(f"Channel of inappropriate format: {channel}")
    else:
        return channel


def get_reactions(msg: Message):
    if msg.reactions is not None:
        reactions = msg.reactions.results
        d = {}
        for reaction in reactions:
            d[reaction.reaction] = reaction.count
        return d
    return None


async def get_channel_name(client: TelegramClient, entity):
    # https://stackoverflow.com/questions/61456565/how-to-get-the-chat-or-group-name-of-incoming-telegram-message-using-telethon
    """

    :param client:
    :param entity (`str` | `int` | :tl:`Peer` | :tl:`InputPeer`):
                If a username or invite link is given, **the library will
                use the cache**. This means that it's possible to be using
                a username that *changed* or an old invite link (this only
                happens if an invite link for a small group chat is used
                after it was upgraded to a mega-group).

                If the username or ID from the invite link is not found in
                the cache, it will be fetched. The same rules apply to phone
                numbers (``'+34 123456789'``) from people in your contact list.

                If an exact name is given, it must be in the cache too. This
                is not reliable as different people can share the same name
                and which entity is returned is arbitrary, and should be used
                only for quick tests.

                If a positive integer ID is given, the entity will be searched
                in cached users, chats or channels, without making any call.

                If a negative integer ID is given, the entity will be searched
                exactly as either a chat (prefixed with ``-``) or as a channel
                (prefixed with ``-100``).

                If a :tl:`Peer` is given, it will be searched exactly in the
                cache as either a user, chat or channel.

                If the given object can be turned into an input entity directly,
                said operation will be done.

                Unsupported types will raise ``TypeError``.

                If the entity can't be found, ``ValueError`` will be raised.
    :return:
    """
    entity = await client.get_input_entity(entity)
    chat_full = await client(GetFullChannelRequest(entity))
    if hasattr(chat_full, 'chats') and len(chat_full.chats) > 0:
        chat_title = chat_full.chats[0].title
        return chat_title


async def get_channel_link(client: TelegramClient, entity):
    """
    :param client:
    :param entity (`str` | `int` | :tl:`Peer` | :tl:`InputPeer`):
                If a username or invite link is given, **the library will
                use the cache**. This means that it's possible to be using
                a username that *changed* or an old invite link (this only
                happens if an invite link for a small group chat is used
                after it was upgraded to a mega-group).
                If the username or ID from the invite link is not found in
                the cache, it will be fetched. The same rules apply to phone
                numbers (``'+34 123456789'``) from people in your contact list.
                If an exact name is given, it must be in the cache too. This
                is not reliable as different people can share the same name
                and which entity is returned is arbitrary, and should be used
                only for quick tests.
                If a positive integer ID is given, the entity will be searched
                in cached users, chats or channels, without making any call.
                If a negative integer ID is given, the entity will be searched
                exactly as either a chat (prefixed with ``-``) or as a channel
                (prefixed with ``-100``).
                If a :tl:`Peer` is given, it will be searched exactly in the
                cache as either a user, chat or channel.
                If the given object can be turned into an input entity directly,
                said operation will be done.
                Unsupported types will raise ``TypeError``.
                If the entity can't be found, ``ValueError`` will be raised.
    :return:
    """
    entity = await client.get_input_entity(entity)
    chat_full = await client(GetFullChannelRequest(entity))
    if hasattr(chat_full, 'chats') and len(chat_full.chats) > 0:
        username = chat_full.chats[0].username
        return f"https://t.me/{username}"


async def get_channel_id(client: TelegramClient, entity):
    """

    :param client:
    :param entity (`str` | `int` | :tl:`Peer` | :tl:`InputPeer`):
                If a username or invite link is given, **the library will
                use the cache**. This means that it's possible to be using
                a username that *changed* or an old invite link (this only
                happens if an invite link for a small group chat is used
                after it was upgraded to a mega-group).

                If the username or ID from the invite link is not found in
                the cache, it will be fetched. The same rules apply to phone
                numbers (``'+34 123456789'``) from people in your contact list.

                If an exact name is given, it must be in the cache too. This
                is not reliable as different people can share the same name
                and which entity is returned is arbitrary, and should be used
                only for quick tests.

                If a positive integer ID is given, the entity will be searched
                in cached users, chats or channels, without making any call.

                If a negative integer ID is given, the entity will be searched
                exactly as either a chat (prefixed with ``-``) or as a channel
                (prefixed with ``-100``).

                If a :tl:`Peer` is given, it will be searched exactly in the
                cache as either a user, chat or channel.

                If the given object can be turned into an input entity directly,
                said operation will be done.

                Unsupported types will raise ``TypeError``.

                If the entity can't be found, ``ValueError`` will be raised.

    :return:
    """
    entity = await client.get_input_entity(entity)
    return int('-100' + str(entity.channel_id))
    # print(await client.get_peer_id('me'))  # your id


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


async def get_source_channel_name_for_message(client: TelegramClient, msg: Message):
    try:
        if isinstance(msg.fwd_from, MessageFwdHeader):
            if msg.fwd_from.from_id is not None:
                orig_name = await get_channel_name(client, msg.fwd_from.from_id.channel_id)
            elif msg.fwd_from.from_name is not None:
                orig_name = msg.fwd_from.from_name
            else:
                logger.error(f'Failed to define the origins of the message\n{msg.stringify()}')
                orig_name = 'Undefined'
            orig_date = msg.fwd_from.date
            fwd_to_name = await get_channel_name(client, msg.chat_id)
            fwd_date = msg.date
        else:
            orig_name = await get_channel_name(client, msg.chat_id)
            orig_date = msg.date
            fwd_to_name, fwd_date = None, None
    except:
        logger.error(f"Failed to get source channel name and date\n{msg.stringify()}", exc_info=True)
        return None, None, None, None

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


def start_client(client_name='default_client', **start_kwargs):
    is_not_connected = True
    connection_attempts = 1
    while is_not_connected:
        try:
            logger.debug(f"Connection attempt: {connection_attempts}")
            client = TelegramClient(client_name, config.api_id, config.api_hash)
            client.start(**start_kwargs)
            logger.debug('TelegramClient is started\n')
            is_not_connected = False
        except:
            connection_attempts += 1
            logger.error(f"Was not able to start a client '{client_name}'", exc_info=True)
            time.sleep(30)

    return client


def list_to_str_newline(ls):
    return '\n'.join([str(el) for el in ls])


async def get_user_display_name(client: TelegramClient, entity):
    entity = await client.get_entity(entity)
    if isinstance(entity, types.User):
        return tutils.get_display_name(entity)
    elif isinstance(entity, types.Chat):
        # TODO: fix overhead
        return get_channel_name(entity)
    else:
        raise ValueError(f"entity of type {type(entity)} is not processed for extracting display_name")
