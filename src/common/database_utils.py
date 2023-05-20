import nest_asyncio

from src.common.channel import Channel

nest_asyncio.apply()

import json
import os
from collections import defaultdict
import datetime
from typing import List, Dict

import csv
import aiofiles
from aiocsv import AsyncDictWriter

from telethon.tl.patched import Message
from telethon.errors import UserNotParticipantError, ChannelInvalidError
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import ExportChatInviteRequest

import emoji

from src.common.utils import (list_to_str_newline, extract_msg_features)
from src.common.get_project_root import get_project_root

import logging

logger = logging.getLogger(__name__)

USERS_FILEPATH = "src/data/users.json"
FEEDS_FILEPATH = "src/data/feeds.json"
LAST_CHANNEL_MESSAGE_ID_FILEPATH = 'src/data/last_channel_message_id.json'
LAST_BOT_MESSAGE_ID_FILEPATH = 'src/data/last_bot_message_id.json'
RB_FILTER_LISTS_FILEPATH = 'src/data/rule_based_filter_lists.json'
TRANSACTIONS_FILEPATH = 'src/data/transactions.csv'


def get_last_bot_id():
    root = get_project_root()
    path = os.path.join(root, LAST_BOT_MESSAGE_ID_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    else:
        data = 410
    return data


def save_last_bot_ids(value: int):
    root = get_project_root()
    path = os.path.join(root, LAST_BOT_MESSAGE_ID_FILEPATH)

    with open(path, 'w') as f:
        json.dump(value, f)
    logger.log(5, 'saved updated bot message ids')


def get_last_channel_ids():
    root = get_project_root()
    path = os.path.join(root, LAST_CHANNEL_MESSAGE_ID_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(lambda: 0, {int(k): v for k, v in json.load(f).items()})  # a la deserializer
    else:
        data = defaultdict(lambda: 0)
    return data


def save_last_channel_ids(channels: dict):
    root = get_project_root()
    path = os.path.join(root, LAST_CHANNEL_MESSAGE_ID_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(k): v for k, v in channels.items()}, f)
    logger.log(5, 'saved updated channel ids')


def update_last_channel_ids(ch_id: int, last_msg_id: int):
    """

    :param ch_id: channel id
    :param last_msg_id:
    :return:
    """
    channels = get_last_channel_ids()
    channels[ch_id] = last_msg_id
    save_last_channel_ids(channels)
    return channels


def get_users():
    root = get_project_root()
    path = os.path.join(root, USERS_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(list, {int(k): v for k, v in json.load(f).items()})  # a la deserializer
    else:
        data = defaultdict(list)
    return data


def update_users(users_dict, channel_id: int, user: int = None, add_not_remove=True):
    # TODO: add ceiling for the number of channels for the user
    # rn the structure of users is "user_id": [int(channel_id), int(channel_id)] because of JSON limitations
    # actually, all IDs are int
    if not str(channel_id).startswith('-100'):
        raise ValueError(f"Channel has to start from '-100'. Given: {str(channel_id)}")

    if add_not_remove:  # adding the channel to user's reading list
        if channel_id in users_dict[user]:
            logger.warning(f"Channel {channel_id} is already in subs list of {user} user")
        else:
            users_dict[user].append(channel_id)
            logger.debug(f"User {user} added channel {channel_id}. Now user's list: {users_dict[user]}")
    else:
        if user is None:  # remove this channel for all users
            for user_key, users_channels in users_dict.items():
                before_len = len(list(users_dict[user_key]))
                after = [c for c in users_dict[user_key] if c != channel_id]
                if len(after) < before_len:
                    users_dict[user_key] = after
                    logger.debug(f"Removed channel {channel_id} from user {user_key}. Now user's list: {after}")
        else:  # remove the channel for a desired user
            users_dict[user] = [c for c in users_dict[user] if c != channel_id]
            logger.debug(f"User {user} removed channel {channel_id}. Now user's list: {users_dict[user]}")
        # TODO: remove user if empty? Or if empty and didn't start the conversation with the bot (not in session)
        #  or request a confirmation
    return users_dict


def save_users(data):
    root = get_project_root()
    path = os.path.join(root, USERS_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(k): v for k, v in data.items()}, f)
        logger.debug('saved users')


def get_channel_owner(ch_id: int):
    users = get_users()
    owners = [k for k, v in users.items() if ch_id in v]
    if owners:
        return owners[0]
    else:
        return None


def get_feeds():
    root = get_project_root()
    path = os.path.join(root, FEEDS_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(list, {int(k): v for k, v in json.load(f).items()})  # a la deserializer
    else:
        data = defaultdict(list)
    return data


def update_feed(feeds, dst_ch: Channel, src_ch=None, add_not_remove=True):
    # TODO: check if save if always triggered anyway. move it here
    if add_not_remove:
        if src_ch.id in feeds[dst_ch.id]:
            logger.warning(
                f"Channel {src_ch.id} ({src_ch.id}) is already in subs list of {dst_ch.id} ({dst_ch.id}) channel")
        else:
            feeds[dst_ch.id].append(src_ch.id)
            reading_list_links = []
            for ch_id in feeds[dst_ch.id]:
                ch = Channel(channel_id=ch_id)
                reading_list_links.append(ch.link)
            logger.debug(
                f'updated {dst_ch!r}. Updated list:\n{list_to_str_newline(reading_list_links)}')
    else:
        if src_ch is None:  # full remove of the dst_ch
            feeds.pop(dst_ch.id, None)  # feeds may not contain this channel at all if there are no subs for it
            logger.debug(f'Permanently removed {dst_ch!r} from feeds')
        else:
            feeds[dst_ch.id] = [c for c in feeds[dst_ch.id] if c != src_ch.id]
            logger.debug(f'Removed {src_ch!r} from {dst_ch!r} feeds')
    return feeds


def save_feeds(data):
    root = get_project_root()
    path = os.path.join(root, FEEDS_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(k): v for k, v in data.items()}, f)
        logger.debug('saved feeds')


def invert_feeds(feeds: Dict[int, List[int]], client: TelegramClient) -> Dict[int, List[int]]:
    scr2dst = {}
    for dst_ch_id, src_ch_id_list in feeds.items():
        for src_ch_id in src_ch_id_list:
            with client:
                src_ch = Channel(channel_id=src_ch_id, client=client)
                dst_ch = Channel(channel_id=dst_ch_id, client=client)
            scr2dst.setdefault(src_ch, []).append(dst_ch)
    return scr2dst


def get_rb_filters():
    root = get_project_root()
    path = os.path.join(root, RB_FILTER_LISTS_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(list, json.load(f))
    else:
        data = defaultdict(list)
    return data


def get_transaction_template():
    """
    Acts like a schema for the destination file
    Warning! If the order is changed here, the transactions CSV will fail. You have to allign both of them

    Returns
    -------

    """
    d = {'transaction_id': None,
         'processing_timestamp': None,
         'action': None,  # action (added sub\removed sub\started bot\added bot to channel) (only if channel action)

         'user_id': None,
         'user_channel_id': None,
         'user_channel_link': None,
         'user_channel_name': None,

         'src_channel_id': None,
         'src_channel_link': None,
         'src_channel_name': None,
         'src_forwarded_from_original_timestamp': None,
         'src_channel_message_id': None,
         'pinned_in_src_channel': None,  # renamed: pinned -> pinned_in_src_channel
         'src_channel_message_grouped_id': None,  # renamed: grouped_id
         'src_channel_message_is_grouped': None,  # renamed: grouped

         'original_content': None,
         'original_channel_id': None,
         'original_channel_link': None,
         'original_channel_name': None,
         'original_post_timestamp': None,
         'original_channel_message_id': None,  # (none if channel action?) renamed: message_id to original_channel_message_id
         # add group ID if given in the original

         'message_text': None,  # actually also should have src_channel or original_channel
         'empty_text': None,
         'media': None,
         'media_type': None,
         'entities': None,
         'entities_num': None,

         'filtered_by_common_rb': None,
         'filtered_by_personal_rb': None,
         'filtered_by_hist': None,
         'filtered_by_ml': None}
    return d


# check if dir exist if not create it
def check_dir(file_name):
    directory = os.path.dirname(file_name)
    if not os.path.exists(directory):
        os.makedirs(directory)


async def dict_to_csv_async(d: List[dict], filepath: str):
    # dictionary keys order is extremely important!
    # TODO: add check that fields are the same
    check_dir(filepath)
    if not os.path.isfile(filepath):
        logger.info(f"Creating a new file for: {filepath}")
        async with aiofiles.open(filepath, mode="w", encoding="utf-8", newline="") as afp:
            writer = AsyncDictWriter(afp, fieldnames=list(d[0].keys()), restval="NULL", quoting=csv.QUOTE_ALL)
            await writer.writeheader()

    # dict writing, all quoted, "NULL" for missing fields
    async with aiofiles.open(filepath, mode="a", encoding="utf-8", newline="") as afp:
        writer = AsyncDictWriter(afp, fieldnames=list(d[0].keys()), restval="NULL", quoting=csv.QUOTE_ALL)
        await writer.writerows(d)


async def log_messages(client: TelegramClient, msg_list_before: List[Message],
                       filtering_details: dict,
                       **kwargs):
    assert len(msg_list_before) == len(filtering_details)

    rows = []
    for msg in msg_list_before:
        row_dict = get_transaction_template()  # and update it with extract_msg_features
        row_dict['processing_timestamp'] = datetime.datetime.now()

        msg_features = await extract_msg_features(msg, client)
        # msg_features.pop('media')
        # msg_features.pop('entities')
        for k in list(msg_features):
            if emoji.is_emoji(k):
                msg_features.pop(k)
        row_dict.update(msg_features)

        if filtering_details[msg.id] is None:  # change to already extracted src_channel_message_id?
            row_dict['action'] = 'forward'
        elif filtering_details[msg.id] == 'rb':
            row_dict['action'] = 'filter'
            row_dict['filtered_by_personal_rb'] = True
        elif filtering_details[msg.id] == 'hist':
            row_dict['action'] = 'filter'
            row_dict['filtered_by_hist'] = True
        elif 'recommender_' in filtering_details[msg.id]:
            row_dict['action'] = 'filter'
            row_dict['filtered_by_ml'] = True

        len_before = len(row_dict)
        row_dict.update(kwargs)
        len_after = len(row_dict)
        if len_before != len_after:
            logger.error(f'During logging the shape of the log dict changed from {len_before} (expected) to '
                         f'{len_after} (actual')

        rows.append(row_dict)

    root = get_project_root()
    path = os.path.join(root, TRANSACTIONS_FILEPATH)
    await dict_to_csv_async(d=rows, filepath=path)
    logger.log(5, "Saved transactions for messages")


async def delete_users_channel(event, channel: Channel, clients: List[TelegramClient]):
    # remove channel from users
    users = get_users()
    users = update_users(users_dict=users, channel_id=channel.id, user=None, add_not_remove=False)
    save_users(users)

    # remove feeds for the channel
    feeds = get_feeds()
    update_feed(feeds, dst_ch=channel, src_ch=None, add_not_remove=False)
    save_feeds(feeds)

    # TODO: remove from the cache as well to avoid collisions with the same new name

    # remove bot from the channel. but the bot may be even not added
    try:
        for client in clients:
            async with client:
                # Deletes a dialog (leaves a chat or channel).
                await client.delete_dialog(channel.id)
                # notify the user
                await event.reply(f"Channel {channel.name} is removed from the database")  # sent twice
                logger.info(f'{await client.get_me()} successfully quit from {channel!r}')
    except ChannelInvalidError:
        logger.error('Invalid channel object. Make sure to pass the right types, for instance making sure that the '
                     'request is designed for channels or otherwise look for a different one more suited '
                     '(caused by GetChannelsRequest)')
    except UserNotParticipantError:
        logger.error(f'Bot is not a member of {channel} (caused by LeaveChannelRequest)')
    except:
        logger.error('Unable to quit the dialog and notify the user', exc_info=True)


def remove_source_channel(feeds):
    return feeds
    # remove from: feeds of all dst users. Notify the user
    # remove from: channels cache. anyway it's not observable anymore
    # remove from: last_channel_message_id


if __name__ == '__main__':
    import sys
    from src import config

    # to try with a pure session like if a new user laucnes it
    # client = start_client('database_utils_user_client')
    # used as main not at the same time as the main_feed.py
    client_path = os.path.join(get_project_root(), 'src/telefeed_client')
    # client_path = os.path.join(get_project_root(), f'src/bot_for_feed_{config.bot_id}')
    client = TelegramClient(client_path, config.api_id, config.api_hash)

    # ch = Channel(channel_id=-1001809422952)
    # print('size', sys.getsizeof(ch))
    print(f'Owner of {-1001320078862} is {get_channel_owner(-1001320078862)}')
    print(f'Owner of {-1001843444088} is {get_channel_owner(-1001843444088)}')

    with client:
        # input_entity = Channel(parsable="https://t.me/data_secrets", client=client, restore_values=True, force_request=False)
        # ch = Channel(parsable="https://t.me/data_secrets", client=client, restore_values=True, force_update=True)
        # input_entity = Channel.get_input_entity_offline(client=client, peer="https://t.me/durov")
        # ch2 = Channel(parsable="-1001668629777", client=client, restore_values=True, force_update=True)

        # ch3 = Channel(parsable="https://t.me/sansara_channel", client=client, restore_values=True, force_update=True)
        ch3 = Channel(channel_id=-1001177342537, client=client, restore_values=True, force_update=True)
        ch4 = Channel(channel_id=-1001830001000, client=client, restore_values=True, force_update=False)
        ch5 = Channel(channel_id=-1001830001000, client=client, restore_values=True, force_update=True)
        # ch4 = Channel(parsable="-1001180675167", client=client, restore_values=True, force_update=True)

        # chat_entity = client.get_entity("https://t.me/some_private_link")
        # result = client(GetFullChannelRequest(channel=chat_entity))

    with client:
        inv_link = client(ExportChatInviteRequest(peer=-1001668629777))  # only owner can do for private channels

    # res = asyncio.get_event_loop().run_until_complete(client._get_entity_from_string("https://t.me/labelmedata"))
    # entity = asyncio.get_event_loop().run_until_complete(client.get_entity("https://t.me/meduzalive"))
    # print('entity', entity)

    ch = Channel(parsable="https://t.me/meduzalive", client=client)
    print(ch)
    print('size', sys.getsizeof(ch))
