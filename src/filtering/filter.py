import asyncio
import os
import re
from copy import deepcopy

from typing import List
from telethon.tl.patched import Message
from telethon.sync import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage, MessageMediaPoll

from src.common.utils import get_history, get_message_origins, get_project_root
from src.common.database_utils import get_rb_filters, Channel

import logging
logger = logging.getLogger(__name__)

HTML_pattern = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')


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
        # TODO: check what defines a unique poll
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


def message_is_duplicated(msg: Message, history_messages: List[Message], client: TelegramClient):
    try:
        for history_msg in history_messages:
            if message_is_same(history_msg, msg):  # TODO: check the case where TypeError: 'NoneType' object is not subscriptable (approximately for history_msg)
                # the rest of the function is for debugging purposes
                orig_channel_id1, orig_name1, orig_date1, _, fwd_to_channel_id1, fwd_to_name1, fwd_date1, _ = asyncio.get_event_loop().run_until_complete(get_message_origins(client, history_msg))
                orig_channel_id2, orig_name2, orig_date2, _, fwd_to_channel_id2, fwd_to_name2, fwd_date2, _ = asyncio.get_event_loop().run_until_complete(get_message_origins(client, msg))
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
                else:  # channel 1 has forwarded post at fwd_date1 date
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
    except:
        logger.error(f'unable to run message_is_duplicated\nhistory_msg\n{history_msg.stringify()}\n\nmsg\n{msg.stringify()}', exc_info=True)
        return False


def message_is_filtered_by_rules(msg: Message, rules_list: List[str]):
    """
    Checks if the message contains content to filter. If fails, returns False (to keep) result.
    Each rule is compared in lowercase against the message
    :param msg:
    :param rules_list:
    :return:
    """
    if msg.message is None:
        logger.warning("An empty message came to a message_is_filtered_by_rules function")
        return False

    try:
        for phrase in rules_list:
            if msg.message.lower().find(phrase.lower()) != -1:
                logger.info(f"Message id {msg.id} is filtered according to the rule: {phrase}")
                return True
        return False
    except:
        logger.error(f"Failed to check the message against the phrase {phrase}:\n{msg}", exc_info=True)
        return False


class Filter:
    def __init__(self, rule_base_check=True, history_check=True, client: TelegramClient=None, dst_ch: Channel = None,
                 use_common_rules=True, postfix_template_to_ignore=None):
        """

        Parameters
        ----------
        rule_base_check
        history_check
        client : TelegramClient, default None
            User client from the main feed. Rich client with long history helps avoiding dead queries.
        dst_ch
        use_common_rules
        """
        self.rule_base_check = rule_base_check
        self.use_common_rules = use_common_rules
        self.history_check = history_check
        self.client = client
        self.dst_ch = dst_ch
        self.postfix_re_pattern_to_ignore = self._postfix_template2pattern(postfix_template_to_ignore)
        # TODO: apart from adapting text, we need to remove the entities we added...

        if self.rule_base_check:
            self.checkrules_list = self._get_rb_list()
            if self.checkrules_list == []:
                logger.debug("There are no advertising\\filtering rules to check")

        if self.history_check and (self.client is None):
            raise ValueError("If history check is performed, 'client' parameter has to be provided")
        if self.history_check and (self.dst_ch is None):
            raise ValueError("If history check is performed, 'dst_ch' parameter has to be provided")

    @staticmethod
    def _postfix_template2pattern(postfix_template_to_ignore):
        if postfix_template_to_ignore is None:
            return None

        def cleanhtml(raw_html):
            cleantext = re.sub(HTML_pattern, '', raw_html)
            return cleantext

        template = cleanhtml(postfix_template_to_ignore)
        pattern = re.sub(r"\{.*?\}", r".*", template)
        return pattern

    def _remove_postfix(self, msg: Message):
        if self.postfix_re_pattern_to_ignore is None:
            return msg
        message_postfix_match = re.search(self.postfix_re_pattern_to_ignore, msg.message)
        if message_postfix_match:
            # new_msg = deepcopy(msg)
            new_msg = msg
            new_msg.message = re.sub(self.postfix_re_pattern_to_ignore, '', new_msg.message)  # remove end of text
            new_msg.entities = [e for e in new_msg.entities if e.offset < message_postfix_match.start()]  # TODO: check border
            if len(new_msg.entities) == 0:
                new_msg.entities = None
            return new_msg
        else:
            return msg

    def _get_rb_list(self, ) -> List:
        all_rules = get_rb_filters()
        rules = []
        if self.use_common_rules:
            rules += all_rules['_common_rb_list']
        if self.dst_ch is not None:
            rules += all_rules[str(self.dst_ch.id)]  # TODO: serialize during reading above?
        return rules

    def filter_messages(self, msg_list: List[Message]) -> List[Message]:
        """
        Returns messages in the original order.

        :param msg_list:
        :return:
        """
        filtering_details = {k.id: None for k in msg_list}
        len_before = len(msg_list)

        # TODO: mb split common/personal rb
        if self.rule_base_check and self.checkrules_list != []:
            logger.log(5, f"Performing a rule-based filtering for {self.dst_ch!r}")
            msg_list, filtering_details = self._filter(msg_list, filter_func=message_is_filtered_by_rules,
                                                       filtering_details=filtering_details, filter_name='rb',
                                                       rules_list=self.checkrules_list)
        if msg_list and self.history_check:
            logger.debug(f"Performing a history filtering for {self.dst_ch!r}")
            # history has to be more or less global and extended after every message forwarded to my channel
            # instead of querying every time
            dst_channel_history_messages = asyncio.get_event_loop().run_until_complete(get_history(client=self.client, entity=self.dst_ch.id, limit=100))
            dst_channel_history_messages = [msg for msg in dst_channel_history_messages if msg.action is None]  # filter out channel creation, voice calls, etc.
            dst_channel_history_messages = [self._remove_postfix(msg) for msg in dst_channel_history_messages]
            msg_list, filtering_details = self._filter(msg_list, filter_func=message_is_duplicated,
                                                       filtering_details=filtering_details, filter_name='hist',
                                                       history_messages=dst_channel_history_messages,
                                                       client=self.client)
        if len_before != len(msg_list):
            logger.debug(f'Before filtering: {len_before}. After: {len(msg_list)}')
        return msg_list, filtering_details

    def _filter(self, msg_list: List[Message], filter_func, filtering_details,
                filter_name, **filter_func_kwargs) -> List[Message]:
        """
        From a list of messages which was planned to be sent removes the ones according to the filter_func.
        If at least one of the messages in the group is filtered out, the whole group will be dropped
        as well.

        :param msg_list:
        :param filter_func:
        :param filter_func_kwargs:
        :return:
        """
        msg_list_clean = []
        to_drop_group_id = -1
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
                    msg_list_clean.append(msg)
                else:
                    logger.log(5, f'removed an indirect spam message from to_drop group {to_drop_group_id}. '
                                  f'To_drop message:\n{to_drop_message[:20]}')
                    to_drop_message_ids.append(msg.id)
        logger.log(5, f'to_drop_message_ids: {to_drop_message_ids}')

        after_check_drop_list = []
        for msg in msg_list_clean:
            if msg.grouped_id in to_drop_groups_after_check:
                after_check_drop_list.append(msg)
        if after_check_drop_list:
            logger.info('Some message was filtered in the middle of the group')
            msg_list_clean = [msg for msg in msg_list_clean if msg not in after_check_drop_list]

        msg_list_clean.reverse()  # for consistency, msg_list is always descending

        # None for passing messages, filter_name from the previous or the current step if filtered out
        filtering_details = {
            msg_id: (v if v is not None or msg_id in [m.id for m in msg_list_clean] else filter_name) for
            msg_id, v in
            filtering_details.items()}

        return msg_list_clean, filtering_details


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(module)s %(levelname)s: %(message)s',
        level=logging.INFO,
        datefmt='%a %d.%m.%Y %H:%M:%S',
        force=True)
    logging.getLogger(__name__).setLevel('DEBUG')

    from src.common.utils import start_client
    from telethon.tl.functions.messages import GetHistoryRequest

    # https://arabic-telethon.readthedocs.io/en/stable/extra/advanced-usage/mastering-telethon.html#asyncio-madness
    # used as main not at the same time as the main_feed.py
    user_client_path = os.path.join(get_project_root(), 'src/telefeed_client')
    client = start_client(user_client_path)

    # my_channel_history = get_history(client=client, peer=config.MyChannel, limit=10)
    dst_ch = Channel(channel_link='https://t.me/DeepStuffChannel', client=client)
    filtering_component = Filter(rule_base_check=True, history_check=True, client=client, dst_ch=dst_ch)

    to_filter_messages = client(GetHistoryRequest(
        peer='https://t.me/DeepFaker',  # https://t.me/DeepFaker
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=50,
        max_id=0,
        min_id=0,
        hash=0
    ))

    messages = to_filter_messages.messages
    messages_checked_list, filtering_details = filtering_component.filter_messages(messages)
    print(f'Before {len(messages)}. After {len(messages_checked_list)}')
    print('filtering_details', filtering_details)
