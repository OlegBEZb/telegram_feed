from telethon import TelegramClient

from src import config

bot_client = TelegramClient('bot', config.api_id, config.api_hash)
NO_ARG_CLI_COMMANDS = {
    # command: [button_name, help_descr]
    '/start': ["🆕 start", "Registers the users and sends the greetings message"],

    '/help_text': ["🤓 textual help (CLI)",
                   'Gives you information about the available commands in text.'],

    '/about': ["ℹ️ about", "Sends the detailed description of the project and its usage"],

    '/my_channels': ["🗒️ show my channels",
                     "This command shows all your channels which fetch updates from this bot"],
}
ARG_CLI_COMMANDS = {'/channel_info': ["⚙️ show channel info",
                                      (
                                          "This command shows source channels for one of your channels. "
                                          "This command requires 1 argument "
                                          "from you: link to your channel."
                                          "\nExample: /channel_info t.me/your_destination_channel")],

                    # make an n-step procedure with the first command "config bog"
                    '/add_to_channel': ["➕ add source channel to my channel",
                                        (
                                            "This command adds a new source channel which content will be redirected to your channel."
                                            " This command requires 2 arguments from you: what channel to add and where to add. These two"
                                            " arguments are both links to telegram channels."
                                            "\nExample: /add_to_channel t.me/channel_of_interest t.me/your_destination_channel")], }
CLI_COMMANDS = dict(NO_ARG_CLI_COMMANDS, **ARG_CLI_COMMANDS)
ADMIN_COMMANDS = {
    # these commands should be available and visible only for devs
    '/users': 'Lists users',
    '/send_all': '',
    '/send_stats': ''
}
PRIVATE_INFO_MESSAGE = ("**Note**: your private information is not visible in any way for "
                        "other users but still visible for the bot creator for debugging purposes. In future, this "
                        "personal information will be private for everyone including admins and developers")
START_MESSAGE = (
        "Welcome to the 'telefeed' project. To start using the bot, you have to add it as an administrator to your "
        "**public** channel. If you don't have any, create one. For **each** created channel you will be able "
        "to get personalised feed.\n" + PRIVATE_INFO_MESSAGE)
ABOUT_MESSAGE = ("The purpose of this bot is to aggregate all your channels into one feed, as well as filter ads "
                 "and duplicated content.\n"
                 "We recommend adding the bot to **separate** thematic channels (news, games, art, etc.) for better "
                 "recommendations. "
                 "To receive even more relevant content, you can allow reactions on your public channel and use them "
                 "for the content published. You can use any reaction which describes your (surprisingly) reaction the "
                 "best but the most important reactions for our recommender system are '👍' and '👎' - use them "
                 "if you like or dislike the content. To indicate spam, use '💩' and '🤬'. This will be used for further "
                 "filtering.\n" + PRIVATE_INFO_MESSAGE)
FEEDBACK_MESSAGE = "Your feedback is appreciated.\nPlease, contact t.me/OlegBEZb regarding any issues"
