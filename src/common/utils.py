import time
import os

from telethon import TelegramClient
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.patched import Message
from telethon.tl.types import MessageFwdHeader, ReactionEmoji, ReactionCustomEmoji
from telethon.errors.rpcerrorlist import ChannelPrivateError, FloodWaitError

from src import config

import logging

from src.common.channel import get_display_name, Channel
from src.common.get_project_root import get_project_root

logger = logging.getLogger(__name__)


def get_reactions(msg: Message):
    """
    If only one reaction is allowed, then through all the ReactionCount objects there will be only one with
    chosen_order=0 while the remaining will have chosen_order=None. This chosen_order will always be zero for the
    last selected reaction.
    Important to note that in case of album, reaction is given to the textual message (first one).

    Parameters
    ----------
    msg

    Returns
    -------

    """
    if msg.reactions is not None:
        reactions = msg.reactions.results
        d = {}
        for reaction in reactions:
            if isinstance(reaction.reaction, ReactionEmoji):
                d[reaction.reaction.emoticon] = reaction.count
            elif isinstance(reaction.reaction, ReactionCustomEmoji):
                d[reaction.reaction.document_id] = reaction.count
        return d
    return None


# TODO: extension to the end of the group. https://stackoverflow.com/questions/74084075/telethon-or-pyrogram-forward-whole-album-instead-of-last-media-without-caption
# TODO: add limit -1 for the whole history
# TODO: accept Channel as argument and try to restore with ID first, and link second. Only after that return exception
async def get_history(client: TelegramClient, channel: Channel = None, **get_history_request_kwargs) -> 'hints.TotalList':
    """
    Accepts channel or entity inside the kwargs. Channel has higher weight and ID and link from it will be used.
    But anything may be passed: channel may be None and kwargs have entity
    For reference: https://core.telegram.org/api/offsets.

    :param client: only user client is accepted
    :param entity: Target peer. Works well with channel link, ID. ID works only if it is registered in the .session.
    :param offset_id: Only return messages starting from the specified message ID
    :param offset_date: Only return messages sent before the specified date
    :param add_offset: Number of list elements to be skipped, negative values are also accepted.
    :param limit: Number of results to return. A limit on the number of objects to be returned, typically
    between 1 and 100. When 0 is provided the limit will often default to an intermediate value like ~20.
    :param max_id: If a positive value was transferred, the method will return only messages with IDs less than
    max_id
    :param min_id: 	If a positive value was transferred, the method will return only messages with IDs more than
    min_id

    Parameters
    ----------
    channel

    """
    get_history_default = {'offset_id': 0, 'offset_date': 0,
                           'add_offset': 0, 'limit': 1,
                           'max_id': 0, 'min_id': 0}  # min and max ids 0 or -1?
    # the dict on the right takes precedence
    get_history_request_kwargs = get_history_default | get_history_request_kwargs

    candidate_kwargs = []
    if channel is not None:
        if channel.id is not None:
            candidate_kwargs.append(get_history_request_kwargs | {'entity': channel.id})
        if channel.link is not None:
            candidate_kwargs.append(get_history_request_kwargs | {'entity': channel.link})
    if 'entity' in get_history_request_kwargs:
        candidate_kwargs.append(get_history_request_kwargs)

    for kw in candidate_kwargs:
        try:
            messages = await client.get_messages(**kw)
            break
        except ChannelPrivateError:
            logger.error(f'Tried to perform get_history on a private/banned channel. User client has to be a part of it. '
                         f'get_history_request_kwargs\n{get_history_request_kwargs}')  # may be even public but your bot has to be added
            raise
        except FloodWaitError as e:
            logger.info(f'Got FloodWaitError cause by GetHistoryRequest. Have to sleep {e.seconds} seconds / {e.seconds / 60:.1f} minutes / '
                        f'{e.seconds / 60 / 60:.1f} hours\nget_history_request_kwargs\n{get_history_request_kwargs}')
            raise
        except:
            logger.error(f'Unknown fail in get_history. client:\n{await client.get_me()}\nget_history_request_kwargs\n{get_history_request_kwargs}', exc_info=True)
            # raise

    return messages


# TODO: not use name here at all. Only ID. Everything else is to be found by Channel
async def get_message_origins(client: TelegramClient, msg: Message):
    orig_channel_id = None
    orig_name = None

    fwd_to_name = None
    try:
        if isinstance(msg.fwd_from, MessageFwdHeader):  # if message was forwarded to a place where we got it
            if msg.fwd_from.from_id is not None:
                orig_channel_id = int('-100' + str(msg.fwd_from.from_id.channel_id))
            elif msg.fwd_from.from_name is not None:
                orig_name = msg.fwd_from.from_name

            fwd_to_channel_id = msg.chat_id
            orig_date = msg.fwd_from.date
            fwd_date = msg.date
            orig_post_id = msg.fwd_from.channel_post
            fwd_to_post_id = msg.id
        else:  # this message is original
            orig_date = msg.date
            orig_channel_id = msg.chat_id
            orig_post_id = msg.id
            fwd_to_channel_id, fwd_to_name, fwd_date, fwd_to_post_id = None, None, None, None
    except:
        logger.error(f"Failed to get source channel name and date\n{msg.stringify()}", exc_info=True)
        return None, None, None, None, None, None

    orig_channel = Channel(channel_id=orig_channel_id, channel_name=orig_name, client=client)
    fwd_to_channel = Channel(channel_id=fwd_to_channel_id, channel_name=fwd_to_name, client=client)
    return orig_channel, orig_date, orig_post_id, fwd_to_channel, fwd_date, fwd_to_post_id


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
            logger.debug(f'TelegramClient is started with the session file: {client_name}')
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
        result_dict.update({'empty_text': True, 'message_text': ''})  # why empty string is selected?
    else:
        result_dict.update({'empty_text': False})

    if result_dict['grouped_id'] is None:
        result_dict['grouped'] = False
    else:
        result_dict['grouped'] = True

    if client is not None:
        orig_channel, orig_date, orig_post_id, fwd_to_channel, fwd_date, fwd_to_post_id = await get_message_origins(client, msg)

        result_dict['original_channel_id'] = orig_channel.id
        result_dict['original_channel_link'] = orig_channel.link
        result_dict['original_channel_name'] = orig_channel.name

        result_dict['original_post_timestamp'] = orig_date  # TODO: add difference with the time of processing
        if fwd_to_channel.name is None:
            result_dict['src_channel_id'] = orig_channel.id
            result_dict['src_channel_link'] = orig_channel.link
            result_dict['src_channel_name'] = orig_channel.name

            result_dict['src_forwarded_from_original_timestamp'] = None

            result_dict['original_content'] = True
        else:
            result_dict['src_channel_id'] = fwd_to_channel.id
            result_dict['src_channel_link'] = fwd_to_channel.link
            result_dict['src_channel_name'] = fwd_to_channel.name

            result_dict['src_forwarded_from_original_timestamp'] = fwd_date

            result_dict['original_content'] = False

        # TODO: infer original_channel_id	original_channel_link? If original_content, from src_channel, otherwise -
        #  using Channel initialization

    reactions_dict = get_reactions(msg)  # may cause different amounts of fields
    if reactions_dict is not None:  # may be updated without checking if None?
        result_dict.update(reactions_dict)

    result_dict['entities'] = msg.entities
    if msg.entities is not None:
        result_dict['entities_num'] = len(msg.entities)
    else:
        result_dict['entities_num'] = 0

    return result_dict


if __name__ == '__main__':
    import asyncio

    # used as main not at the same time as the main_feed.py
    user_client_path = os.path.join(get_project_root(), 'src/telefeed_client')
    client = start_client(user_client_path)

    messages = asyncio.get_event_loop().run_until_complete(
        get_history(client=client, channel=None, min_id=68326 - 10, entity=-1001099860397, limit=30))

    messages = asyncio.get_event_loop().run_until_complete(
        get_history(client=client, channel=None, entity='https://t.me/myfavoritejumoreski', limit=11))

    messages = asyncio.get_event_loop().run_until_complete(
        get_history(client=client, channel=None, entity=-1001143742161, limit=11))

    messages = asyncio.get_event_loop().run_until_complete(
        get_history(client=client, channel=Channel(channel_id=-1001143742161), limit=11))


    # asyncio.get_event_loop().run_until_complete(client.send_message('me', 'Hello to myself!'))

    # res = asyncio.get_event_loop().run_until_complete(client._get_entity_from_string("https://t.me/labelmedata"))
    # res = asyncio.get_event_loop().run_until_complete(client._get_entity_from_string("-1001389289917"))
    res = asyncio.get_event_loop().run_until_complete(client.get_entity(-1001143742161))
    res = asyncio.get_event_loop().run_until_complete(client.get_entity('LabelMe - DataScience blog'))
    # res = asyncio.get_event_loop().run_until_complete(client.get_entity("+31643198671"))
    # res = asyncio.get_event_loop().run_until_complete(client._get_entity_from_string("+31643198671"))
