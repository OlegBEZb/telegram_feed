import json
import os
from collections import defaultdict
import datetime
from typing import List


import csv
import aiofiles
from aiocsv import AsyncDictWriter


from telethon.tl.patched import Message
from telethon.sync import TelegramClient

from src.utils import check_channel_correctness, get_project_root, get_message_origins

import logging
logger = logging.getLogger(__name__)

USERS_FILEPATH = "./data/users.json"
FEEDS_FILEPATH = "src/data/feeds.json"
LAST_CHANNEL_MESSAGE_ID_FILEPATH = './data/last_channel_message_id.json'
RB_FILTER_LISTS_FILEPATH = 'src/data/rule_based_filter_lists.json'
TRANSACTIONS_FILEPATH = 'src/data/transactions.csv'


def get_last_channel_ids():
    if os.path.exists(LAST_CHANNEL_MESSAGE_ID_FILEPATH):
        with open(LAST_CHANNEL_MESSAGE_ID_FILEPATH, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(lambda: 0, json.load(f))
    else:
        data = defaultdict(lambda: 0)
    return data


def save_last_channel_ids(channels: dict):
    with open(LAST_CHANNEL_MESSAGE_ID_FILEPATH, 'w') as f:
        json.dump(channels, f)
    logger.debug('saved updated channel ids')


def update_last_channel_ids(key, last_msg_id):
    channels = get_last_channel_ids()
    channels[key] = last_msg_id
    save_last_channel_ids(channels)
    return channels


def get_users():
    if os.path.exists(USERS_FILEPATH):
        with open(USERS_FILEPATH, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(list, json.load(f))
    else:
        data = defaultdict(list)
    return data


def update_user(users_dict, user, channel_id=None, add_not_remove=True):
    # TODO: add ceiling for the number of channels for the user
    # rn the structure of users is "user_id": [int(channel_id), int(channel_id)]
    if isinstance(user, int):
        user = str(user)
    if not str(channel_id).startswith('-100'):
        raise ValueError(f"Channel has to start from '-100'. Given: {str(channel_id)}")

    if add_not_remove:
        if channel_id in users_dict[user]:
            logger.warning(f"Channel {channel_id} is already in subs list of {user} user")
        else:
            users_dict[user].append(channel_id)
            logger.debug(f"User {user} added channel {channel_id} to {users_dict[user]}")
    else:
        users_dict[user] = [c for c in users_dict[user] if c != channel_id]
        logger.debug(f"User {user} removed channel {channel_id} from {users_dict[user]}")
    return users_dict


def save_users(data):
    with open(USERS_FILEPATH, 'w') as f:
        logger.debug(f'updated users\n{data}')
        json.dump(data, f)


def get_feeds():
    root = get_project_root()
    path = os.path.join(root, FEEDS_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(list, json.load(f))
    else:
        data = defaultdict(list)
    return data


def update_feed(feeds, dst_ch, src_ch, add_not_remove=True):
    # TODO: add ceiling for the number of sources for the channel
    # just in case once again
    src_ch, dst_ch = check_channel_correctness(src_ch), check_channel_correctness(dst_ch)
    if add_not_remove:
        if src_ch in feeds[dst_ch]:
            logger.warning(f"Channel {src_ch} is already in subs list of {dst_ch} channel")
        else:
            feeds[dst_ch].append(src_ch)
    else:
        feeds[dst_ch] = [c for c in feeds[dst_ch] if c != src_ch]
    return feeds


def save_feeds(data):
    root = get_project_root()
    path = os.path.join(root, FEEDS_FILEPATH)

    with open(path, 'w') as f:
        json.dump(data, f)
    logger.debug(f'updated channels\n{data}')


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
    d = {'transaction_id': None,
         'processing_timestamp': None,
         'action': None,  # action (added sub\removed sub\started bot\added bot to channel) (only if channel action)

         'user_id': None,
         'user_channel_id': None,
         'user_channel_name': None,

         'src_channel_id': None,
         'src_channel_name': None,
         'src_forwarded_from_original_timestamp': None,

         'original_channel_id': None,
         'original_channel_name': None,
         'original_post_timestamp': None,

         'message_id': None,  # (none if channel action)
         'message_text': None,
         
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
    for m in msg_list_before:
        row_dict = get_transaction_template()
        row_dict['processing_timestamp'] = datetime.datetime.now()
        # row_dict['user_channel_name'] = dst_ch
        row_dict['src_channel_message_id'] = m.id
        row_dict['message_text'] = m.message

        orig_name, orig_date, fwd_to_name, fwd_date = await get_message_origins(client, m)
        if fwd_to_name is None:
            row_dict['src_channel_name'] = orig_name
            row_dict['original_channel_name'] = orig_name
            row_dict['original_post_timestamp'] = orig_date
        else:
            row_dict['src_channel_name'] = fwd_to_name
            row_dict['original_channel_name'] = orig_name

            row_dict['original_post_timestamp'] = orig_date
            row_dict['src_forwarded_from_original_timestamp'] = fwd_date

        if filtering_details[m.id] is None:
            row_dict['action'] = 'forward'
        elif filtering_details[m.id] == 'rb':
            row_dict['action'] = 'filter'
            row_dict['filtered_by_personal_rb'] = True
        elif filtering_details[m.id] == 'hist':
            row_dict['action'] = 'filter'
            row_dict['filtered_by_hist'] = True

        row_dict.update(kwargs)

        rows.append(row_dict)

    root = get_project_root()
    path = os.path.join(root, TRANSACTIONS_FILEPATH)
    await dict_to_csv_async(d=rows, filepath=path)
    logger.debug("Saved transactions for messages")
