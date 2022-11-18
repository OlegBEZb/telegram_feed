from telethon import events, types, Button
import telethon.utils as tutils

import config

import logging

from src import bot_client
from src.bot_menu_utils import COMMANDS
from utils import check_channel_correctness, list_to_str_newline, get_channel_link, get_user_display_name
from src.database_utils import get_users, update_user, save_users, get_feeds, update_feed, save_feeds

logging.basicConfig(
    # filename="BotClient.log",
    format='%(asctime)s %(module)s %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%a %d.%m.%Y %H:%M:%S',
    force=True)
logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logging.getLogger('telethon').setLevel(logging.WARNING)

PRIVATE_INFO_MESSAGE = ("**Note**: your private information is not visible in any way for "
                        "other users but still visible for the bot creator for debugging purposes. In future, this "
                        "personal information will be private for everyone including admins and developers")

START_MESSAGE = ("Welcome to the 'telefeed' project. You have to add this bot as an administrator to your "
                 "**public** channel. If you don't have any, create one. For each created channel you will be able "
                 "to get personalised feed.\n"+PRIVATE_INFO_MESSAGE)

ABOUT_MESSAGE = ("The purpose of this bot is to aggregate all your channels into one feed, as well as filter ads "
                 "and duplicated content. "
                 "For better recommendations, you can allow reactions on your public channel and use them for the "
                 "content published. You can use any reaction which describes your (surprisingly) reaction the "
                 "best but the most important reactions for our recommender system are '👍' and '👎' - use them "
                 "if you like or dislike the content. To indicate spam, use '💩' and '🤬'. This will be used for further "
                 "filtering.\n" + PRIVATE_INFO_MESSAGE)


# TODO: move to a separate file and dynamically add to the list of handlers like in
# https://github.com/Lonami/TelethonianBotExt
# these commands should be available and visible only for devs
ADMIN_COMMANDS = {
    'users': 'Lists users'
}

# to be dynamic
# from bot_menu_utils import command_help_test, button_channel_info
# bot_client.add_event_handler(command_help_test, events.NewMessage(pattern='/hlep'))
# bot_client.add_event_handler(button_channel_info, events.CallbackQuery(data=b"/channel_info"))
bot_client.start(bot_token=config.bot_token)
logger.info('bot started')


# ChatAction only handles MessageService in this case, what's the chat type you're adding to. removal should be decided by Telegram.
# You can use Raw and handle UpdateChannel*
# A broadcast channel doesn't have action messages opposite of groups. and Telegram api is very changing, ChatAction
# needs to support those new changes at some point. since remove actions aren't sent.

# @client.on(events.Raw(telethon.types.UpdateBotChatInviteRequester))
# async def approve(e):
#     await client(functions.messages.HideChatJoinRequestRequest(e.peer, e.user_id, approved=True or False
#       )
# )


# needed to catch all kinds of events related to bots because for some reason these events are
# not covered well with standard methods
# @bot_client.on(events.Raw)
# async def handler(update):
#     # Print all incoming updates
#     print(update.stringify())


@bot_client.on(events.Raw(types.UpdateChannelParticipant))
# ChannelParticipant, ChannelParticipantSelf, ChannelParticipantCreator, ChannelParticipantAdmin, ChannelParticipantBanned, ChannelParticipantLeft
async def update_channel_participant(e):
    channel_id = int('-100' + str(e.channel_id))
    if e.new_participant:
        # TODO: decide with chat_id types: int or str
        if isinstance(e.new_participant, types.ChannelParticipantAdmin) and e.new_participant.user_id == config.bot_id:
            logger.info(f"Bot is added as admin at '{channel_id}' due to '{e.actor_id}'s action")

            users = get_users()
            users = update_user(users, e.actor_id, channel_id, add_not_remove=True)
            save_users(users)

    elif e.prev_participant:
        if isinstance(e.prev_participant, types.ChannelParticipantAdmin) and e.prev_participant.user_id == config.bot_id:
            logger.info(f"Bot is no longer an admin at '{channel_id}' due to '{e.actor_id}'s action")

            users = get_users()
            users = update_user(users, e.actor_id, channel_id, add_not_remove=False)
            save_users(users)
            # TODO: remove related records from the DB (feeds, etc.)


@bot_client.on(events.CallbackQuery(data=b"/help"))
@bot_client.on(events.NewMessage(pattern='/help'))
async def command_help(event):
    sender_id = event.chat_id
    if not event.is_private:  # make a wrapper
        await event.reply(
            "Contact me in PM to get the help menu",
            buttons=[[Button.url("Click me for help!", config.bot_url)]],
        )
        return

    help_text = "The following commands are available: \n"
    for key, comment in COMMANDS.items():  # generate help text out of the commands dictionary defined at the top
        help_text += key + ": "
        help_text += comment[1] + "\n\n"
    await bot_client.send_message(sender_id, help_text)
    logger.debug(f"Sent help to {await get_user_display_name(bot_client, int(sender_id))} ({sender_id})")


@bot_client.on(events.CallbackQuery(data=b"/start"))
# @bot_client.on(events.CallbackQuery(pattern=b"/start"))  # works as well
# @bot_client.on(events.CallbackQuery(pattern=r"/start"))  # works as well
@bot_client.on(events.NewMessage(pattern='/start'))
async def command_start(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    await bot_client.send_message(sender_id, START_MESSAGE)
    users = get_users()
    if str(sender_id) not in users:  # if user hasn't used the "/start" command yet:
        users[sender_id] = []
        save_users(users)
        await command_help(event)  # show the new user the help page
        logger.info(f"New user {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) started the bot")
    else:
        await bot_client.send_message(sender_id, "I already have you in my database")


@bot_client.on(events.CallbackQuery(data=b"/about"))
@bot_client.on(events.NewMessage(pattern='/about'))
async def command_about(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    await bot_client.send_message(sender_id, ABOUT_MESSAGE)
    logger.debug(f"Sent about to {await get_user_display_name(bot_client, int(sender_id))} ({sender_id})")


@bot_client.on(events.CallbackQuery(pattern='/channel_info'))  # with argument, pattern or data makes the difference
@bot_client.on(events.NewMessage(pattern='/channel_info'))
async def command_channel_info(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return

    if isinstance(event.original_update, types.UpdateNewMessage):
        message = event.message.text
    elif isinstance(event.original_update, types.UpdateBotCallbackQuery):  # or types.UpdateBot...
        message = event.data.decode('utf-8')  # according to the doc

    try:
        _, dst_ch = message.split()
        dst_ch = check_channel_correctness(dst_ch)
    except:
        await event.reply(f"Was not able to process the argument. Check /help once again:\n{COMMANDS['/channel_info'][1]}")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) failed in command_channel_info", exc_info=True)
        return

    # dst_ch_id = get_channel_id(bot, dst_ch)
    entity = await bot_client.get_input_entity(dst_ch)
    dst_ch_id = tutils.get_peer_id(entity)

    users = get_users()
    if dst_ch_id not in users[str(sender_id)]:
        await event.reply("You are not allowed to perform this action")
        return

    feeds = get_feeds()
    reading_list = feeds[dst_ch]
    if not reading_list:
        await event.reply("Your reading list is empty")
    else:
        await event.reply(f"Your reading list of {len(reading_list)} item(s) (sorted chronologically):\n{list_to_str_newline(reading_list)}")
    logger.debug(f"{await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) called /channel_info")


@bot_client.on(events.CallbackQuery(data=b"/my_channels"))
@bot_client.on(events.NewMessage(pattern='/my_channels'))
async def command_my_channels(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    users = get_users()
    users_channels = users[str(sender_id)]
    if len(users_channels) == 0:
        await event.reply("You haven't added the bot to any of your channels yet")
    else:
        users_channels_links = [await get_channel_link(bot_client, ch) for ch in users_channels]
        await event.reply(f"Your channels (sorted chronologically):\n{list_to_str_newline(users_channels_links)}")
    logger.debug(f"{await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) called /my_channels")


@bot_client.on(events.NewMessage(pattern='/add_to_channel'))
async def command_add_to_channel(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        await event.reply("Communication with the bot has to be performed only in direct messages, not public channels")
        return
    try:
        message = event.message
        # TODO: add any number of channels before the last/destination one
        _, src_ch, dst_ch = message.text.split()
        # TODO: add assert for the incorrect format
        src_ch, dst_ch = check_channel_correctness(src_ch), check_channel_correctness(dst_ch)

        entity = await bot_client.get_input_entity(dst_ch)
        dst_ch_id = tutils.get_peer_id(entity)
        # dst_ch_id = get_channel_id(bot, dst_ch)

        users = get_users()
        if dst_ch_id not in users[str(sender_id)]:
            await event.reply("You are not allowed to perform this action. Try to add the bot to your channel as admin.")
            return

        feeds = get_feeds()

        if src_ch in feeds:
            # TODO: think about potential solution
            await event.reply("You can not add somebody's target channel as your source because of potential infinite loops")
            return

        update_feed(feeds, dst_ch, src_ch, add_not_remove=True)
        save_feeds(feeds)
        # TODO: add notification that the channel was already there
        await event.reply(f"Added! Now your reading list is the following:\n{list_to_str_newline(feeds[dst_ch])}")
        logger.debug(f"User {sender_id} added {src_ch} to {dst_ch}", exc_info=True)
    except:
        await event.reply("Was not able to add channel. Check if your destination channel is public and the bot is added as admin")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) failed to perform /add_to_channel with the following command: \"{message.text[:100]}\"", exc_info=True)
        return


@bot_client.on(events.NewMessage(pattern='/users'))
async def admin_command_users(event):
    if not isinstance(event.chat, types.User):
        return
    sender_id = event.chat_id
    if int(sender_id) != config.my_id:
        await event.reply("You are not allowed to perform this action")
        return
    users = get_users()
    if len(users) == 0:
        await event.reply("You don't have any yet")
    else:
        # TODO: add the number of channels per user
        user_names = [await get_user_display_name(bot_client, int(u)) for u in users]
        rows = [f"{name:.<18} ({user_id}) - {len(channels):.>5} channel(s)" for name, user_id, channels in zip(user_names, users, users.values())]
        await event.reply(f"Your {len(users)} user(s) (sorted chronologically):\n{list_to_str_newline(rows)}")


@bot_client.on(events.NewMessage)  # UpdateNewMessage
async def echo_all(event):
    sender_id = event.chat_id
    if not isinstance(event.chat, types.User):
        return
    message = event.message
    cmd = message.text.split()[0]
    if cmd not in COMMANDS:
        # await event.reply("This is an unrecognized command. Use /help to list all available commands")
        logger.error(f"User {await get_user_display_name(bot_client, int(sender_id))} ({sender_id}) called an unrecognized command", exc_info=True)


bot_client.run_until_disconnected()
