import asyncio
from copy import deepcopy

from typing import List
from telethon.tl.patched import Message
from telethon.sync import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage, MessageMediaPoll

from src.utils import get_history, get_source_channel_name_for_message
from src.database_utils import get_rb_filters
from src import config

import logging
logger = logging.getLogger(__name__)


def media_is_duplicated(m1, m2):
    if m1 is None and m2 is None:
        return True

    if type(m1) is not type(m2):  # TODO: video may be compared to gif or image, for example
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
    elif isinstance(m1, MessageMediaPoll):
        d1 = m1.poll.to_dict()
        d2 = m2.poll.to_dict()
    else:
        logger.error(f"Media with types {type(m1)}, {type(m2)} can't be processed. Return 'no duplicate'")
        return False

    # file reference is different. https://core.telegram.org/api/file_reference
    d1.pop('file_reference', None)
    d2.pop('file_reference', None)
    # drop date as well?
    if d1 == d2:
        return True
    # else:
    #     from telethon.tl.tlobject import TLObject
    #     logger.error(f'm1 type {type(m1)} or m2 type {type(m2)} is not TLObject')

    return False


def message_is_same(msg1: Message, msg2: Message):
    is_duplicated = False  # presumption of innocence

    if msg1.media is None:
        if msg2.media is None:
            if msg1.message == msg2.message and msg1.entities == msg2.entities:  # may be empty and None respectively
                is_duplicated = True
    else:
        if msg2.media is not None:
            # if both media are presented, it's enough to judge regardless of text
            is_duplicated = media_is_duplicated(msg1.media, msg2.media)

    if is_duplicated:
        logger.debug('Found a duplicate')

    return is_duplicated


def message_is_duplicated(msg: Message, history, client: TelegramClient):
    for history_msg in history.messages:
        if message_is_same(history_msg, msg):
            # the rest of the function is for debugging purposes
            orig_name1, orig_date1, fwd_to_name1, fwd_date1 = asyncio.get_event_loop().run_until_complete(get_source_channel_name_for_message(client, history_msg))
            orig_name2, orig_date2, fwd_to_name2, fwd_date2 = asyncio.get_event_loop().run_until_complete(get_source_channel_name_for_message(client, msg))
            if fwd_to_name1 is None:  # channel 1 has it's own post
                if fwd_to_name2 is None:  # channel 2 has it's own post
                    if orig_date1 > orig_date2:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was published by '{orig_name2}' before '{orig_name1}'")
                    else:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was published by '{orig_name1}' before '{orig_name2}'")
                else:  # channel 2 has forwarded post
                    if orig_date1 > fwd_date2:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was published by '{fwd_to_name2}' (forwarded from '{orig_name2}') before '{orig_name1}'")
                    else:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was published by '{orig_name1}' before '{fwd_to_name2} (forwarded from '{orig_name2}')")
            else:  # channel 1 has forwarded post
                if fwd_to_name2 is None:  # channel 2 has it's own post
                    if fwd_date1 > orig_date2:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was published by '{orig_name2}' before '{fwd_to_name1}' (forwarded from '{orig_name1}')")
                    else:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was published by '{fwd_to_name1}' (forwarded from '{orig_name1}') before '{orig_name2}'")
                else:  # channel 2 has forwarded post
                    if fwd_date1 > fwd_date2:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was reposted by '{fwd_to_name2}' at {fwd_date2} (from '{orig_name2}') before '{fwd_to_name1}' at {fwd_date1} (from '{orig_name1}')")
                    else:
                        logger.debug(
                            f"Message '{history_msg.message[:20]}...' was reposted by '{fwd_to_name1}' at {fwd_date1} (from '{orig_name1}') before '{fwd_to_name2}' at {fwd_date2} (from '{orig_name2}')")
            return True
    return False


def message_is_filtered_by_rules(msg: Message, rules_list: List[str]):
    """
    Checks if the message contains content to filter. If fails, returns False (to keep) result.
    Each rule is compared in lowercase against the message
    :param msg:
    :param rules_list:
    :return:
    """
    try:
        for phrase in rules_list:
            if msg.message.lower().find(phrase.lower()) != -1:
                logger.info(f"Message id {msg.id} is filtered according to the rule: {phrase}")
                return True
        return False
    except:
        logger.error(f"Failed to check the message {msg} against the phrase {phrase}")
        return False


class Filter:
    def __init__(self, rule_base_check=True, history_check=True, client: TelegramClient=None, dst_channel=None,
                 use_common_rules=True):
        self.rule_base_check = rule_base_check
        self.use_common_rules = use_common_rules
        self.history_check = history_check
        self.client = client
        self.dst_channel = dst_channel

        if self.rule_base_check:
            self.checkrules_list = self._get_rb_list()
            if self.checkrules_list == []:
                logger.debug("There are no advertising\\filtering rules to check")

        if self.history_check and (self.client is None):
            raise ValueError("If history check is performed, 'client' parameter has to be provided")
        if self.history_check and (self.dst_channel is None):
            raise ValueError("If history check is performed, 'dst_channel' parameter has to be provided")

    def _get_rb_list(self, ) -> List:
        all_rules = get_rb_filters()
        rules = []
        if self.use_common_rules:
            rules += all_rules['_common_rb_list']
        if self.dst_channel is not None:
            rules += all_rules[self.dst_channel]  # TODO: check flatness
        return rules

    def filter_messages(self, msg_list: List[Message]) -> List[Message]:
        """
        Returns messages in the original order.

        :param msg_list:
        :return:
        """
        # TODO: move filtering_details logic to the _filter function and mb split common/personal rb
        msg_list_before = deepcopy(msg_list)

        if self.rule_base_check and self.checkrules_list != []:
            logger.log(5, f"Performing a rule-based filtering for {self.dst_channel}")
            msg_list = self._filter(msg_list, filter_func=message_is_filtered_by_rules, rules_list=self.checkrules_list)
            filtering_details = {k.id: (None if k.id in [m.id for m in msg_list] else 'rb') for k in msg_list_before}
            msg_list_before = deepcopy(msg_list)
        if msg_list and self.history_check:
            logger.debug(f"Performing a history filtering for {self.dst_channel}")
            # have to be more or less global and extended after every message forwarded to my channel
            dst_channel_history = get_history(client=self.client, peer=self.dst_channel, limit=100)
            msg_list = self._filter(msg_list, filter_func=message_is_duplicated,
                                    history=dst_channel_history, client=self.client)
            # (v if v is not None or k in [m.id for m in msg_list] else 'hist')
            # we keep None for the normal messages, 'hist' for the ones filtered on this step, and we preserve 'rb'
            # from the prev step
            filtering_details = {k: (v if v is not None or k in [m.id for m in msg_list] else 'hist') for k, v in filtering_details.items()}

        return msg_list, filtering_details

    def _filter(self, msg_list: List[Message], filter_func, **filter_func_kwargs) -> List[Message]:
        """
        From a list of messages which was planned to be sent removes the ones according to the filter_func.
        If at least one of the messages in the group is filtered out, the whole group will be dropped
        as well.

        :param msg_list:
        :param filter_func:
        :param filter_func_kwargs:
        :return:
        """
        msg_list_filtered = []
        to_drop_group_id = -1
        to_drop_message = None
        to_drop_message_ids = []

        # when a message from a message group to be filtered but some messages from this group have already passed
        to_drop_groups_after_check = []

        # starting from the oldest. for grouped, the first is text
        for msg in reversed(msg_list):
            if filter_func(msg, **filter_func_kwargs):
                if msg.grouped_id is not None:
                    to_drop_group_id = msg.grouped_id
                    to_drop_groups_after_check.append(to_drop_group_id)
                    to_drop_message = msg.message
                to_drop_message_ids.append(msg.id)
            else:
                if msg.grouped_id != to_drop_group_id:  # no group also counts
                    msg_list_filtered.append(msg)
                else:
                    logger.debug(
                        f'removed an indirect spam message from to_drop group {to_drop_group_id}. To_drop message:\n{to_drop_message[:20]}')
                    to_drop_message_ids.append(msg.id)
        logger.log(5, f'to_drop_message_ids: {to_drop_message_ids}')

        after_check_drop_list = []
        for msg in msg_list_filtered:
            if msg.grouped_id in to_drop_groups_after_check:
                after_check_drop_list.append(msg)
        if after_check_drop_list:
            logger.info('Some message was filtered in the middle of the group')
            msg_list_filtered = [msg for msg in msg_list_filtered if msg not in after_check_drop_list]

        msg_list_filtered.reverse()  # for consistency, msg_list is always descending
        return msg_list_filtered


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(module)s %(levelname)s: %(message)s',
        level=logging.INFO,
        datefmt='%a %d.%m.%Y %H:%M:%S',
        force=True)
    logging.getLogger(__name__).setLevel('DEBUG')

    from src.utils import start_client
    from telethon.tl.functions.messages import GetHistoryRequest

    # https://arabic-telethon.readthedocs.io/en/stable/extra/advanced-usage/mastering-telethon.html#asyncio-madness
    import telethon.sync
    client = start_client('telefeed_client')

    my_channel_history = get_history(client=client, peer=config.MyChannel, limit=50)
    filtering_component = Filter(rule_base_check=True, history_check=True, client=client,
                                 dst_channel='https://t.me/DeepStuffChannel'
                                 )

    to_filter_messages = client(GetHistoryRequest(
        peer='https://t.me/DeepFaker',
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=20,
        max_id=0,
        min_id=0,
        hash=0
    ))

    messages = to_filter_messages.messages
    messages_checked_list, filtering_details = filtering_component.filter_messages(messages)
    print(f'Before {len(messages)}. After {len(messages_checked_list)}')
    print('filtering_details', filtering_details)
