import asyncio
import nest_asyncio
nest_asyncio.apply()

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
from telethon.errors.rpcerrorlist import ChannelPrivateError

from src.common.utils import check_channel_link_correctness, get_project_root, get_message_origins, list_to_str_newline, start_client

import logging

logger = logging.getLogger(__name__)

USERS_FILEPATH = "src/data/users.json"
FEEDS_FILEPATH = "src/data/feeds.json"
LAST_CHANNEL_MESSAGE_ID_FILEPATH = 'src/data/last_channel_message_id.json'
RB_FILTER_LISTS_FILEPATH = 'src/data/rule_based_filter_lists.json'
TRANSACTIONS_FILEPATH = 'src/data/transactions.csv'
CHANNEL_CACHE_FILEPATH = 'src/data/channels_cache.json'


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


def update_user(users_dict, user: int, channel_id=None, add_not_remove=True):
    # TODO: add ceiling for the number of channels for the user
    # rn the structure of users is "user_id": [int(channel_id), int(channel_id)] because of JSON limitations
    # actually, all IDs are int
    if not str(channel_id).startswith('-100'):
        raise ValueError(f"Channel has to start from '-100'. Given: {str(channel_id)}")

    if add_not_remove:
        if channel_id in users_dict[user]:
            logger.warning(f"Channel {channel_id} is already in subs list of {user} user")
        else:
            users_dict[user].append(channel_id)
            logger.debug(f"User {user} added channel {channel_id}. Now user's list: {users_dict[user]}")
    else:
        users_dict[user] = [c for c in users_dict[user] if c != channel_id]
        logger.debug(f"User {user} removed channel {channel_id}. Now user's list: {users_dict[user]}")
    return users_dict


def save_users(data):
    root = get_project_root()
    path = os.path.join(root, USERS_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(k): v for k, v in data.items()}, f)
        logger.debug('saved users')


def get_feeds():
    root = get_project_root()
    path = os.path.join(root, FEEDS_FILEPATH)

    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = defaultdict(list, {int(k): v for k, v in json.load(f).items()})  # a la deserializer
    else:
        data = defaultdict(list)
    return data


def update_feed(feeds, dst_ch, src_ch, add_not_remove=True):
    # TODO: check if save if always triggered anyway. move it here
    # TODO: add ceiling for the number of sources for the channel
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
                f'updated channel {dst_ch.link} ({dst_ch.id}). Updated list:\n{list_to_str_newline(reading_list_links)}')
    else:
        feeds[dst_ch.id] = [c for c in feeds[dst_ch.id] if c != src_ch.id]
    return feeds


def save_feeds(data):
    root = get_project_root()
    path = os.path.join(root, FEEDS_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(k): v for k, v in data.items()}, f)


def invert_feeds(feeds: dict[int, List[int]], client: TelegramClient) -> dict[int, List[int]]:
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
    d = {'transaction_id': None,
         'processing_timestamp': None,
         'action': None,  # action (added sub\removed sub\started bot\added bot to channel) (only if channel action)

         'user_id': None,
         'user_channel_id': None,
         'user_channel_name': None,  # rename to link

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
    for msg in msg_list_before:
        row_dict = get_transaction_template()
        row_dict['processing_timestamp'] = datetime.datetime.now()
        row_dict['src_channel_message_id'] = msg.id
        row_dict['message_text'] = msg.message

        orig_name, orig_date, fwd_to_name, fwd_date = await get_message_origins(client, msg)
        if fwd_to_name is None:
            row_dict['src_channel_name'] = orig_name
            row_dict['original_channel_name'] = orig_name
            row_dict['original_post_timestamp'] = orig_date
        else:
            row_dict['src_channel_name'] = fwd_to_name
            row_dict['original_channel_name'] = orig_name

            row_dict['original_post_timestamp'] = orig_date
            row_dict['src_forwarded_from_original_timestamp'] = fwd_date

        if filtering_details[msg.id] is None:
            row_dict['action'] = 'forward'
        elif filtering_details[msg.id] == 'rb':
            row_dict['action'] = 'filter'
            row_dict['filtered_by_personal_rb'] = True
        elif filtering_details[msg.id] == 'hist':
            row_dict['action'] = 'filter'
            row_dict['filtered_by_hist'] = True

        row_dict.update(kwargs)

        rows.append(row_dict)

    root = get_project_root()
    path = os.path.join(root, TRANSACTIONS_FILEPATH)
    await dict_to_csv_async(d=rows, filepath=path)
    logger.debug("Saved transactions for messages")


class Channel:
    """
    Firstly, checks cached values.
    Secondly, tries to make a request and updates the values.
    Otherwise, the channel will be with missed values.
    """
    def __init__(self, parsable=None, channel_id=None, channel_name=None, channel_link=None,
                 is_public=True, restore_values=True, client=None):

        self._client = client
        self.id = channel_id
        self.name = channel_name
        self.link = channel_link  # consider a list of links? invite vs channel?
        self.is_public = is_public
        self.restore_values = restore_values

        if parsable:
            self._parse_from_string(parsable)

        if self.id is None and self.link is None:
            raise ValueError('Either id or link has to be provided to specify a channel')

        if restore_values:
            if self.id is None or self.name is None or (self.link is None and self.is_public):
                self._restore_from_cache()

            if self.id is None or self.name is None or (self.link is None and self.is_public):
                self._update_via_request()

        # not true as most of communications may be performed using ID only. Private channels don't have link at all
        # if self.id is None and self.name is None and self.link is None:
        #     raise ValueError(f"not able to use {self}")

    # await self._client._get_entity_from_string(x)

    def _parse_from_string(self, parsable):
        # TODO: use utils.parse_phone and utils.parse_username
        if self._client is None:
            raise ValueError(f'TelegramClient has to be passed to perform _parse_from_string. Having {self._client}')
        try:
            if parsable.lstrip('-').isdigit():
                parsable = int(parsable)
            entity = asyncio.get_event_loop().run_until_complete(self._client.get_entity(parsable))
            if isinstance(entity, list):
                entity = entity[0]

            if hasattr(entity, 'username') and entity.username is not None:
                self.link = f"https://t.me/{entity.username}"
                self.is_public = True
            else:  # TODO: check as might be falty
                self.is_public = False
            if hasattr(entity, 'title') and entity.title is not None:
                self.name = entity.title
            if hasattr(entity, 'id') and entity.id is not None:
                self.id = int('-100' + str(entity.id))
        except ChannelPrivateError:
            logger.error(f'Failed in _parse_from_string as the channel {self} is private or you are banned')
        except:
            logger.error(f"Unable to parse Channel from string: {parsable}", exc_info=True)

    def _restore_from_cache(self):
        """
        Fully overwrites Channel fields if there is a local match via id or link (in this priority).
        Name is not used as a source of truth as it's not unique.

        Returns
        -------

        """
        channels = get_channels(restore_values=False)

        id_match, link_match = [], []
        for ch in channels:
            if self.id is not None and ch.id == self.id:
                id_match.append(ch)
            elif self.link is not None and ch.link == self.link:  # for private channels link is None
                logger.info(f'Found cached link not having ID: {ch}')
                link_match.append(ch)

        matches = id_match + link_match
        if len(matches) == 0:
            logger.error(f"{self} not found in cache")
        else:
            cached_channel = matches[0]
            self.id = cached_channel.id
            self.name = cached_channel.name
            self.link = cached_channel.link
            self.is_public = cached_channel.is_public  # we may not know if the channel if public knowing only fragments
        logger.log(5, f"Restored {self} from cache")

    def _update_via_request(self):  # TODO: has to be used in a force way for update
        """
        For public channel, restorates link via ID and vice versa, and name via ID afterwards. For private, only
        name via ID

        :return:
        """
        if self._client is None:
            raise ValueError(f'TelegramClient has to be passed to perform _update_via_request. Having {self._client}')
        from src.common.utils import get_channel_id, get_display_name, get_channel_link

        try:
            if self.is_public:
                if self.link is None:
                    self.link = asyncio.get_event_loop().run_until_complete(get_channel_link(self._client, self.id))
                else:
                    self.link = check_channel_link_correctness(self.link)
                    self.id = asyncio.get_event_loop().run_until_complete(get_channel_id(self._client, self.link))

            self.name = asyncio.get_event_loop().run_until_complete(get_display_name(self._client, self.id))

            logger.info(f"Restored {self} via request")
            channels = get_channels(restore_values=False)
            update_channels(channels, self)
        except ChannelPrivateError:
            logger.error(f'Failed to restore as the channel {self} is private or you are banned')

    def __eq__(self, other):
        """Overrides the default implementation"""
        # TODO: probably check both id, name, link fields to update potentially
        if isinstance(other, Channel):
            return (self.id == other.id) and (self.name == other.name) and (self.link == self.link)
        return False

    def __str__(self):
        # TODO: consider something more readable
        return f"""Channel(id={self.id}, name="{self.name}", link="{self.link}", public={self.is_public})"""

    def __repr__(self):
        return f"""Channel(id={self.id}, name="{self.name}", link="{self.link}", public={self.is_public})"""

    def __hash__(self):
        return hash(self.id)


def get_channels(restore_values=True):
    """
    get_entity is a shortcut for GetUsers or in your case GetChannels, it takes a list of InputChannel,
    the id goes to channel_id, but access_hash is what matters. if can't be found in session; request won't be sent.

    You need to have the access_hash stored by yourself if you must delete session file, you can also pass
    get_entity(inputChannel(id, hash)) to skip session check

    :return:
    """
    root = get_project_root()
    path = os.path.join(root, CHANNEL_CACHE_FILEPATH)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            # "id" : {"username": username, "invite_link": invite_link}.
            data = {int(ch_id): v for ch_id, v in json.load(f).items()}  # a la deserializer
    else:
        return None

    channels = [Channel(channel_id=ch_id, channel_name=v['username'], channel_link=v['invite_link'],
                        is_public=v['is_public'], restore_values=restore_values) for ch_id, v in data.items()]
    return channels


def save_channels(channels_list: List[Channel]):
    root = get_project_root()
    path = os.path.join(root, CHANNEL_CACHE_FILEPATH)

    with open(path, 'w') as f:
        json.dump({str(ch.id): {"username": ch.name, "invite_link": ch.link, 'is_public': ch.is_public} for ch in channels_list}, f)
        logger.debug('saved channels cache')


def update_channels(channels_list: List[Channel], target_ch: Channel, add_not_remove=True):
    """


    Parameters
    ----------
    channels_list
    target_ch
    add_not_remove

    Returns
    -------

    """
    # TODO: simplify logic
    if add_not_remove:
        if target_ch not in channels_list:  # firstly, check by full match
            if target_ch.id in [ch.id for ch in channels_list]:
                old_ch = [ch for ch in channels_list if ch.id == target_ch.id][0]
                channels_list.remove(old_ch)
                channels_list.append(target_ch)
                logger.info(f'Cached {target_ch}\ninstead of outdated {old_ch}\nNow have {len(channels_list)} channels cached')
            else:
                channels_list.append(target_ch)
                logger.info(
                    f'Cached a new {target_ch}. Now have {len(channels_list)} channels cached')
            save_channels(channels_list)
        else:
            logger.debug(f'Tried to cache already cached {target_ch}')
    else:
        channels_list = [c for c in channels_list if c != target_ch]
        save_channels(channels_list)

    return channels_list


if __name__ == '__main__':
    import sys

    # to try with a pure session like if a new user laucnes it
    # client = start_client('database_utils_user_client')
    # used as main not at the same time as the main_feed.py
    user_client_path = os.path.join(get_project_root(), 'src/telefeed_client')
    client = start_client(user_client_path)

    ch = Channel(channel_id=-1001036240821)
    print('size', sys.getsizeof(ch))

    res = asyncio.get_event_loop().run_until_complete(client._get_entity_from_string("https://t.me/labelmedata"))
    # entity = asyncio.get_event_loop().run_until_complete(client.get_entity("https://t.me/meduzalive"))
    # print('entity', entity)

    ch = Channel(parsable="https://t.me/meduzalive", client=client)
    print(ch)
    print('size', sys.getsizeof(ch))
