import json
import os
from collections import defaultdict

from src.utils import check_channel_correctness, get_project_root

import logging
logger = logging.getLogger(__name__)

USERS_FILEPATH = "./data/users.json"
FEEDS_FILEPATH = "./data/feeds.json"
LAST_CHANNEL_MESSAGE_ID_FILEPATH = './data/last_channel_message_id.json'
RB_FILTER_LISTS_FILEPATH = 'src/data/rule_based_filter_lists.json'


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
    if os.path.exists(FEEDS_FILEPATH):
        with open(FEEDS_FILEPATH, 'r', encoding='utf-8-sig') as f:
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
    with open(FEEDS_FILEPATH, 'w') as f:
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
