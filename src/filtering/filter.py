from typing import List
from telethon.tl.patched import Message
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage, MessageMediaPoll

from src.utils import logger, OpenJson, get_history, get_source_channel_name_for_message
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


def message_is_duplicated(msg: Message, history, client):
    for history_msg in history.messages:
        if message_is_same(history_msg, msg):
            # the rest of the function is for debugging purposes
            orig_name1, orig_date1, fwd_to_name1, fwd_date1 = get_source_channel_name_for_message(client, history_msg)
            orig_name2, orig_date2, fwd_to_name2, fwd_date2 = get_source_channel_name_for_message(client, msg)
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


def check_messages_with_rules(msg_list: List[Message]) -> List[Message]:
    """
    From a list of messages which was planned to be sent removes the ones according to the rules.
    If at least one of the messages in the group is filtered out, the whole group will be dropped
    as well.
    :param msg_list:
    :return:
    """
    checkrules_list = open_rules_file()

    if checkrules_list is None:
        logger.debug("There are no advertising\\filtering rules to check")
        return msg_list

    messages_checked_list = list()
    spam_group_id = -1
    spam_message = None
    spam_message_ids = []
    for msg in reversed(msg_list):
        if message_is_filtered_by_rules(msg, checkrules_list):
            if msg.grouped_id is not None:
                spam_group_id = msg.grouped_id
                spam_message = msg.message
            spam_message_ids.append(msg.id)
        else:
            if msg.grouped_id != spam_group_id:
                messages_checked_list.append(msg)
            else:
                logger.debug(f'removed message from spam group {spam_group_id}. Spam message\n{spam_message}')
                spam_message_ids.append(msg.id)
    logger.debug('spam_message_ids', spam_message_ids)
    return messages_checked_list


class Filter:
    def __init__(self, rule_base_check=True, history_check=True, client=None):
        self.rule_base_check = rule_base_check
        self.history_check = history_check
        self.client = client

        if self.rule_base_check:
            self.checkrules_list = open_rules_file()  # TODO: add path
            if self.checkrules_list is None:
                logger.debug("There are no advertising\\filtering rules to check")
                raise

        if self.history_check and (self.client is None):
            raise ValueError("If history check is performed, 'client' parameter has to be provided")

    def filter_messages(self, msg_list: List[Message]) -> List[Message]:
        """
        Returns messages in the original order.

        :param msg_list:
        :return:
        """
        # TODO: check order twice
        if self.rule_base_check:
            logger.debug("Performing a rule-based filtering")
            msg_list = self._filter(msg_list, filter_func=message_is_filtered_by_rules, rules_list=self.checkrules_list)
            if len(msg_list) == 0:
                return []
        if self.history_check:
            logger.debug("Performing a history filtering")
            # have to be more or less global and extended after every message forwarded to my channel
            my_channel_history = get_history(client=self.client, peer=config.MyChannel, limit=100)
            msg_list = self._filter(msg_list, filter_func=message_is_duplicated,
                                    history=my_channel_history, client=self.client)
        return msg_list

    def _filter(self, msg_list: List[Message], filter_func, **filter_func_kwargs) -> List[Message]:
        msg_list_filtered = list()
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
                        f'removed an indirect spam message from to_drop group {to_drop_group_id}. To_drop message\n{to_drop_message}')
                    to_drop_message_ids.append(msg.id)
        logger.debug(f'to_drop_message_ids: {to_drop_message_ids}')

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
    from src.utils import start_client
    from telethon.tl.functions.messages import GetHistoryRequest

    # https://arabic-telethon.readthedocs.io/en/stable/extra/advanced-usage/mastering-telethon.html#asyncio-madness
    import telethon.sync
    client = start_client()

    my_channel_history = get_history(client=client, peer=config.MyChannel, limit=50)
    filtering_component = Filter(rule_base_check=True, history_check=True, client=client)

    to_filter_messages = client(GetHistoryRequest(
        peer='https://t.me/cryptovalerii',
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=1,
        max_id=0,
        min_id=0,
        hash=0
    ))

    messages = to_filter_messages.messages
    messages_checked_list = filtering_component.filter_messages(messages)
    print(f'Before {len(messages)}. After {len(messages_checked_list)}')
