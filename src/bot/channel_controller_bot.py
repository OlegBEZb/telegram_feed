import logging
logging.basicConfig(
        # filename="MainClient.log",
        format='%(asctime)s %(module)s %(levelname)s: %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %I:%M:%S',
        force=True)
logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')

import telebot
from telebot import types

# python -m src.bot.channel_controller_bot
from ..utils import check_channel_correctness, get_channel_id, start_client, get_users, save_users, get_feeds, \
    save_feeds

from src.config import bot_token


commands = {  # command description used in the "help" command
    'start'         : 'Get used to the bot',
    'help'          : 'Gives you information about the available commands.'
                      "\nYour feedback is appreciated.\nPlease, contact t.me/OlegBEZb regarding any issues",
    'add_to_channel': "This command adds a new source channel which content will be redirected to your channel."
                      " This command requires 2 arguments from you: what channel to add and where to add. These two"
                      " arguments are both links to telegram channels."
                      "\nExample: /add_to_channel t.me/channel_of_interest t.me/your_destination_channel",
    'channel_info'  : "This command shows source channels for one of your channels. This command requires 1 argument "
                      "from you: link to your channel."
                      "\nExample: /channel_info t.me/your_destination_channel",
}


def is_admin_message(message: telebot.types.Message):
    return bot.get_chat_member(message.chat.id, message.from_user.id).status in ['administrator', 'creator']


def is_admin(chat_id, user_id):
    return bot.get_chat_member(chat_id, user_id).status in ['administrator', 'creator']


bot = telebot.TeleBot(bot_token, parse_mode=None)  # You can set parse_mode by default. HTML or MARKDOWN


# if bot is added to group, this handler will work (for other users added this doesn't work)
# works both in and out. should check that only admin added the bot. and that admin in registered with bot
@bot.my_chat_member_handler()
def my_chat_m(message: types.ChatMemberUpdated):
    first_name = message.from_user.first_name
    # old_status = message.old_chat_member
    new_status = message.new_chat_member
    if isinstance(new_status, types.ChatMemberLeft):
        print('The bot left the chat')
    elif isinstance(new_status, types.ChatMemberAdministrator):
        print("The bot received the needed status")
        if is_admin_message(message):
            users = get_users()
            users[str(message.from_user.id)].append(message.chat.id)
            save_users(users)

    print(f"{first_name} changed {new_status.user.username}'s status in the chat '{message.chat.title}' to {new_status.status}")


# Note: all handlers are tested in the order in which they were declared
@bot.message_handler(commands=['start'])  # commands - messages starting with /
def command_start(message):
    cid = message.chat.id  # chat id or user id finally?
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    username = message.from_user.username

    print(f'User {cid} ({first_name}, {username}) started')
    users = get_users()
    if str(cid) not in users:  # if user hasn't used the "/start" command yet:
        users[message.from_user.id] = []
        save_users(users)
        bot.send_message(cid, "Welcome to the 'telefeed' project. You have to add this bot as an administrator to your channel. "
                              "If you don't have any, create one. For each created channel you will be able to get"
                              " personalised feed")
        command_help(message)  # show the new user the help page
    else:
        bot.send_message(cid, "I already have you in my database")
    # bot.reply_to(message, "Howdy, how are you doing?")


# help page
@bot.message_handler(commands=['help'])
def command_help(m):
    cid = m.chat.id
    help_text = "The following commands are available: \n"
    for key in commands:  # generate help text out of the commands dictionary defined at the top
        help_text += "/" + key + ": "
        help_text += commands[key] + "\n"
    bot.send_message(cid, help_text)  # send the generated help page


@bot.message_handler(commands=['add_to_channel'])
def add_source_to_channel(message):
    _, src_ch, dst_ch = message.text.split()
    src_ch, dst_ch = check_channel_correctness(src_ch), check_channel_correctness(dst_ch)

    users = get_users()
    if dst_ch not in users[str(message.from_user.id)]:
        bot.reply_to(message, f"You are not allowed to perform this action")
        return

    channels = get_feeds()
    channels[dst_ch].append(src_ch)
    save_feeds(channels)
    bot.reply_to(message, f"Added! Now your reading list is the following:\n{channels[dst_ch]}")


@bot.message_handler(commands=['channel_info'])
def channel_info(message):
    _, dst_ch = message.text.split()
    dst_ch = check_channel_correctness(dst_ch)

    client = start_client('../telefeed_client')
    dst_ch_id = get_channel_id(client, dst_ch)
    client.disconnect()
    users = get_users()
    if dst_ch_id not in users[str(message.from_user.id)]:
        bot.reply_to(message, f"You are not allowed to perform this action")
        return

    channels = get_feeds()
    reading_list = channels[dst_ch]
    if not reading_list:
        bot.reply_to(message, f"Your reading list is empty")
    else:
        bot.reply_to(message, f"Your reading list:\n{reading_list}")


@bot.message_handler(func=lambda m: True)
def echo_all(message):
    bot.reply_to(message, message.text)


bot.infinity_polling()
