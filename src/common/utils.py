import time
from typing import Union
from copy import deepcopy
from pathlib import Path

from telethon import TelegramClient, utils as tutils
from telethon.tl.functions.messages import GetHistoryRequest, CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.patched import Message
from telethon.tl.types import MessageFwdHeader
from telethon.errors.rpcerrorlist import ChannelPrivateError
from telethon.tl.types.messages import Messages, MessagesSlice, ChannelMessages, MessagesNotModified

from src import config

import logging
logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    path = Path(__file__).parent.parent.parent
    logger.log(5, f'fetched project root: {path}')
    return Path(__file__).parent.parent.parent


# TODO: check that it's a link
def check_channel_link_correctness(channel_link: str) -> str:
    """
    Checks the correctness of the channel name

    :param channel_link:
    :return:
    """
    channel_link_before = channel_link
    channel_link = channel_link.replace("@", "https://t.me/")
    if channel_link.find("https://t.me/") == -1:
        channel_link = channel_link.replace("t.me/", "https://t.me/")
    if channel_link.find("https://t.me/") == -1:
        # return "error"
        raise ValueError(f"Channel of inappropriate format: {channel_link}")
    logger.debug(f"Checked link: '{channel_link_before}' -> '{channel_link}'")

    return channel_link


def get_reactions(msg: Message):
    if msg.reactions is not None:
        reactions = msg.reactions.results
        d = {}
        for reaction in reactions:
            d[reaction.reaction] = reaction.count
        return d
    return None


async def get_display_name(client: TelegramClient, entity):
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
    # may raise telethon.errors.rpcerrorlist.ChannelPrivateError: The channel specified is private and you lack
    # permission to access it. Another reason may be that you were banned from it (caused by GetChannelsRequest)
    entity = await client.get_entity(entity)
    return tutils.get_display_name(entity)  # works also for users' names


# TODO: vectorize
async def get_channel_link(client: TelegramClient, entity):
    """
    for string it makes a request, for id it only makes one there was stored access_hash in session.
    relevant chats and users are sent with events, if you don't have it in cache, it won't make a request and
    fail locally.

    :param client: works both with bot and personal clients
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
    try:
        # from src.bot.bot_utils import create_channel, transfer_channel_ownership
        # user_client = TelegramClient('telefeed_client', config.api_id, config.api_hash)
        # async with user_client:
        #     entity = await client.get_entity(entity)
        entity = await client.get_entity(entity)
        if hasattr(entity, 'username'):
            if entity.username is None:
                logger.error(f'Channel {entity} has None .username field')
                if entity.title is not None:
                    return entity.title
                else:
                    return f"Unnamed_channel_{entity.id}"
            return f"https://t.me/{entity.username}"
    except:
        logger.error(f'Unable to call client.get_entity with entity:\n{entity}', exc_info=True)


async def get_channel_id(client: TelegramClient, entity) -> int:
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
    # works with channel link, name, integer ID (with and without -100).
    # doesn't work with str ID
    if entity.lstrip('-').isdigit():
        entity = int(entity)
    entity = await client.get_input_entity(entity)
    return int('-100' + str(entity.channel_id))


# TODO: add get_user_id?


# TODO: extension to the end of the group
# TODO: add limit -1 for the whole history
def get_history(client: TelegramClient, **get_history_request_kwargs) -> Union[Messages, MessagesSlice, ChannelMessages,
                                                                               MessagesNotModified]:
    """
    For reference: https://core.telegram.org/api/offsets.

    :param client:
    :param peer: Target peer. Works well with channel link, ID. ID works only if it is registered in the .session.
    Link is preferred.
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

    try:
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
    except:
        logger.error(f'Unknown fail in get_history. get_history_request_kwargs\n{get_history_request_kwargs}',
                     exc_info=True)
        raise

    return messages


async def get_message_origins(client: TelegramClient, msg: Message):
    try:
        if isinstance(msg.fwd_from, MessageFwdHeader):  # if message was forwarded to a place where we got it
            if msg.fwd_from.from_id is not None:
                channel_id = msg.fwd_from.from_id.channel_id
                try:
                    orig_name = await get_display_name(client, channel_id)
                except ChannelPrivateError:
                    logger.error(f'Failed to define the name of the original channel id {channel_id} because of privacy')
                    orig_name = f'_Private_channel_{channel_id}_'
            elif msg.fwd_from.from_name is not None:
                orig_name = msg.fwd_from.from_name
            else:
                logger.error(f'Failed to define the origins of the message\n{msg.stringify()}')
                orig_name = '_Undefined_'
            orig_date = msg.fwd_from.date
            fwd_to_name = await get_display_name(client, msg.chat_id)
            fwd_date = msg.date
        else:  # this message is original
            orig_name = await get_display_name(client, msg.chat_id)
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


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def flatten_iterable(iterable):
    # import itertools
    # return list(itertools.chain.from_iterable(iterable))
    from collections.abc import Iterable
    for x in iterable:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from flatten_iterable(x)
        else:
            yield x


def get_msg_media_type(msg: Message):
    return str(type(msg.media)).split("'")[1].split('.')[-1]


async def extract_msg_features(msg: Message, client: TelegramClient = None, **kwargs):
    result_dict = dict()
    result_dict['src_channel_message_id'] = msg.id
    result_dict['message_text'] = msg.message
    result_dict['pinned'] = msg.pinned
    result_dict['grouped_id'] = msg.grouped_id
    result_dict['media'] = msg.media
    result_dict['media_type'] = get_msg_media_type(msg)

    if result_dict['message_text'] is None:
        result_dict.update({'empty_text': True, 'message_text': ''})
    else:
        result_dict.update({'empty_text': False})

    if result_dict['grouped_id'] is None:
        result_dict['grouped'] = False
    else:
        result_dict['grouped'] = True

    if client is not None:
        orig_name, orig_date, fwd_to_name, fwd_date = await get_message_origins(client, msg)
        result_dict['original_channel_name'] = orig_name
        result_dict['original_post_timestamp'] = orig_date  # TODO: add difference with the time of processing
        if fwd_to_name is None:
            result_dict['src_channel_name'] = orig_name
            result_dict['src_forwarded_from_original_timestamp'] = None

            result_dict['original_content'] = True
        else:
            result_dict['src_channel_name'] = fwd_to_name
            result_dict['src_forwarded_from_original_timestamp'] = fwd_date

            result_dict['original_content'] = False

    reactions_dict = get_reactions(msg)  # may cause different amounts of fields
    if reactions_dict is not None:  # may be updated without checking if None?
        result_dict.update(reactions_dict)

    result_dict['entities'] = msg.entities
    if msg.entities is not None:
        result_dict['entities_num'] = len(msg.entities)
    else:
        result_dict['entities_num'] = 0

    return result_dict
