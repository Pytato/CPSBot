import asyncio
import configparser
import json
import logging
import os
import sys
import time
import yaml
import random
from datetime import datetime
from timeit import default_timer as timer

import discord
from discord.ext import commands

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

startup_begin = timer()

if not os.path.exists("./configs/config.ini"):
    print("No config file can be found in ./configs/.")
    sys.exit("No config found.")

protected_example_addresses = [
    "youremail",
    "your_email",
    "youremailhere",
    "your_email_here",
    "enable",
    "ssc",
    "studentlife",
    "accommodation",
    "parking"
]

config = configparser.ConfigParser()
config.read(os.path.abspath("./configs/config.ini"))
admin_role_names = config["Credentials"]["admin_role_names"]
vote_right_role = config["Credentials"]["vote_rights_role"]
bot_token = config["Credentials"]["bot_token"]
use_drive_for_backup = config["Credentials"]["use_drive_for_backup"]
owner_id = config["Credentials"]["owner_id"]
mute_role_name = config["Misc"]["mute_role_name"]
student_role_name = config["Misc"]["student_role_name"]
delete_messages_after = config["Misc"]["delete_messages_after"]
listen_channels = config["Misc"]["listen_channels"]
announce_channel_config = config["Misc"]["announcement_channel_id"]
cmd_prefix = "££"  # COMMAND PREFIX IS HERE FOR EDITING PURPOSES, UNICODE WAS BEING A FUCK SO THAT'S WHY IT'S HERE

admin_role_list = admin_role_names.split(",")
listen_channels_list = listen_channels.split(",")

if admin_role_list[0] == "":
    print("You must specify administrative roles for this bot.")
    sys.exit("No admin roles defined.")

if listen_channels_list[0] == "":
    listen_channels_list.pop(0)

try:
    use_drive_for_backup = bool(use_drive_for_backup)
except TypeError:
    print("You must enter a boolean type for use_drive_for_backup, remember to capitalise True/False.")

vote_file_queue = []
vote_types = ["freddie_style_vote", "fpbtp_style_vote"]

bot = commands.Bot(command_prefix=cmd_prefix, pm_help=True)


async def auth_with_the_gargle():
    global owner_id

    try:
        owner_id = int(owner_id)
        owner_object = await bot.get_user_info(owner_id)
    except TypeError:
        logger.error("owner_id in config.ini contains non-int type characters.")
        owner_object = None
    except discord.NotFound:
        logger.error("Owner not found from owner_id.")
        owner_object = None

    if owner_object is None:
        logger.error("No owner ID defined")

    await asyncio.sleep(0.4)

    try:
        gauth.LoadCredentialsFile("./configs/credentials.json")
        loaded_creds = True
    except KeyError:
        loaded_creds = False

    if (not loaded_creds) or gauth.credentials is None:
        logger.info("Generating new Google API credentials.")
        if owner_object is not None:
            try:
                logger.debug("OAuth process starting. Messaging bot owner")
                await owner_object.send(
                    "The bot failed automatic authentication with Google's API, please log into console in order to"
                    " re-authenticate manually.")
            except discord.Forbidden:
                logger.error("Could not send message to bot owner, due to them not having DMs enabled.")
        await asyncio.sleep(0.2)
        gauth.CommandLineAuth()

    elif gauth.access_token_expired:
        logger.info("Old access token has expired, refreshing now.")
        gauth.Refresh()
        gauth.Authorize()

    else:
        logger.debug("Authorising app on Google's API")
        gauth.Authorize()

    gauth.SaveCredentialsFile("./configs/credentials.json")


async def search_for_file_drive(file_data, query, make_if_missing=False):
    found_file = False
    await auth_with_the_gargle()
    drive = GoogleDrive(gauth)

    file_list = drive.ListFile(query).GetList()

    requested_file = {"id": None}

    for file in file_list:
        matched_attrib = 0
        for key, value in file_data.items():
            if file[key] == value:
                matched_attrib += 1  # Ensures every parameter is satisfied before the statement is happy.
                if matched_attrib == len(file_data):
                    requested_file = file
                    found_file = True
                    break
        if found_file:
            break

    if (not found_file) and make_if_missing:
        requested_file = drive.CreateFile(file_data)
        requested_file.Upload()

    if requested_file["id"] is None:
        return "Does not exist"

    return requested_file


@bot.event
async def on_ready():
    logger.debug("Start of on_ready()")

    if use_drive_for_backup:
        await auth_with_the_gargle()

    logger.info(f"CPSBot is ready, took {timer() - bot_beginning_time:.3f}s.")


@bot.event
async def on_message(msg):

    if msg.author.bot:
        return

    author_obj = msg.author
    author_is_admin = False
    for admin_role in author_obj.roles:
        if admin_role.name in admin_role_list:
            author_is_admin = True
            break

    message_protected = False
    for protected_address in protected_example_addresses:
        if protected_address in msg.content:
            message_protected = True
            break

    if not message_protected:
        if "@soton.ac.uk" in msg.content and not author_is_admin:
            await msg.channel.send(f"{msg.author.mention}, Please do not send messages in public channels that contain "
                                   f"your email. If you are attempting to verify with SVGEBot, use direct messages and "
                                   f"send:\n\n`!email your_email@soton.ac.uk` then follow instructions sent to your "
                                   f"university inbox. \n\nIf you believe your message was deleted in error, contact "
                                   f"`@Freddie (Pytato)` with the datetime of your message.",
                                   delete_after=delete_messages_after)
            await msg.delete()
            logger.info(f"Auto-deleted message sent by {msg.author.display_name}, in {msg.channel.name}.")

    if listen_channels_list:
        if msg.channel.id not in listen_channels_list and msg.guild is not None:
            return

    if not msg.content.startswith(cmd_prefix):
        return

    logger.debug("Message received from {0.name}#{0.discriminator} in {1.guild}, #{1.channel.name}."
                 .format(msg.author, msg))

    if msg.split(" ")[0] != f"{cmd_prefix}vote_for":
        if not author_is_admin:
            return

    logger.info(f'Command sent by "{msg.author.name}#{msg.author.discriminator}": "{msg.content}."')

    await bot.process_commands(msg)

    await msg.delete()


@bot.command()
async def shutdown(ctx):
    """Shuts the bot down as gracefully as possible."""
    await ctx.send(":wave:", delete_after=1)
    await asyncio.sleep(3)
    await bot.logout()
    sys.exit(0)


@bot.command(name="warn")
async def warn(ctx, target_user_mention, search_depth: int, delete_found_messages: bool, should_mute: bool, *,
               reason: str):
    """This command is used to warn users for breaching the rules, the bot will automatically apply the mute-role
    to the user defined by target_user_id unless instructed otherwise with: "should_mute=False".

    Positional Arguments:
        - target_user_mention is a mention of the command's target
        - search_depth is an integer type that tells the bot how many messages back to search every channel it can see
        in the server.
        - delete_found_messages is a boolean (True/False) that tells the bot whether or not to delete any messages sent
        by the target that it finds.
        - should_mute is a boolean that tells the bot whether or not it should mute the target user.
        - reason is a string type that is used on audit logs where possible and is given to the target by the bot where
        it explains what they did wrong. It is a "catch-all" so should always be the last positional argument.
    """

    warn_command_start = timer()

    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    # Need to get user object for user of given ID.
    target_user = await commands.MemberConverter().convert(ctx, target_user_mention)
    if target_user is None:
        logger.info("Warn command failed: Could not find user from mention.")
        await ctx.send("Command failed: could not find user by given mention.", delete_after=delete_messages_after)
        return

    if reason == "":
        reason = "No reason given."

    try:
        search_depth = int(search_depth)
        delete_found_messages = bool(delete_found_messages)
        should_mute = bool(should_mute)
    except TypeError:
        await ctx.send("Command failed: could not convert argument to correct type.",
                       delete_after=delete_messages_after)

    if not reason.endswith("."):  # Make everything look nice
        reason += "."

    # Before this command embarks on a journey of discovering all the garbage posted by the target, let's see if
    # they're meant to be muted.
    if should_mute:
        mute_role = await commands.RoleConverter().convert(ctx, mute_role_name)
        student_role = await commands.RoleConverter().convert(ctx, student_role_name)
        await target_user.add_roles(mute_role, reason=reason+f" Requested by {ctx.message.author.name}.")
        await target_user.remove_roles(student_role, reason=reason+f" Requested by {ctx.message.author.name}.")
        logger.info(f"Added mute_role to {target_user.display_name}. Requested by {ctx.message.author.name}.")

    target_message_content_list = []
    attachment_file_list = []
    found_messages_count = 0

    target_message_content_list.append("User warned for reason: "+reason)

    async with ctx.message.channel.typing():  # Show the command invoker that the bot is doing something
        message_scrape_timer = timer()
        for channel in ctx.message.guild.text_channels:
            try:
                async for message in channel.history(limit=search_depth):
                    if message.author.id == target_user.id:
                        found_messages_count += 1
                        if message.attachments:
                            message_attach_dir_list = []
                            for attachment in message.attachments:
                                attachment_filename = str(message.author.id)+"_"+attachment.filename
                                with open("./carcinogenic_pictures/"+str(message.id)+"_"+attachment_filename, "w+b") \
                                        as attachment_file:
                                    try:
                                        await attachment.save(attachment_file)
                                        message_attach_dir_list.append("./carcinogenic_pictures/" + str(message.id)+"_"
                                                                       + attachment_filename)
                                        attachment_file_list.append(
                                            "./carcinogenic_pictures/"+str(message.id)+"_"+attachment_filename)
                                    except discord.NotFound:
                                        logger.info(f"Could not find file: {attachment_filename}, message was deleted.")
                                    logger.debug(
                                        f"Saved file with name {attachment_filename} in ./carcinogenic_pictures/")

                            target_message_content_list.append({"id": message.id,
                                                                "timestamp": message.created_at.strftime(
                                                                    "%Y-%m-%d_%H-%M-%S"),
                                                                "contents": message.content,
                                                                "channel": message.channel.id,
                                                                "has_attachment": True,
                                                                "attachment_dir": message_attach_dir_list})
                        else:
                            target_message_content_list.append({"id": message.id,
                                                                "timestamp": message.created_at.strftime(
                                                                    "%Y-%m-%d_%H-%M-%S"),
                                                                "contents": message.content,
                                                                "channel": message.channel.id,
                                                                "has_attachment": False,
                                                                "attachment_dir": []})
                        if delete_found_messages:
                            await message.delete()
            except discord.Forbidden:
                pass
        logger.debug(f"Finished compiling target message history in {timer() - message_scrape_timer} seconds.")

        with open(f"./stored_user_messages/{str(target_user.id)}_{current_time}.json", "w") as json_f:
            json.dump(target_message_content_list, json_f, indent=4)

        if use_drive_for_backup:

            # Need to check if a CPSBot directory has already been made.
            cps_bot_folder = await search_for_file_drive({"title": "CPSBot Cloud",
                                                         "mimeType": "application/vnd.google-apps.folder"},
                                                         {'q': "'root' in parents and trashed=false"},
                                                         make_if_missing=True)

            attachments_folder = await search_for_file_drive({"title": "Saved Attachments",
                                                              "mimeType": "application/vnd.google-apps.folder"},
                                                             {'q': f"'{cps_bot_folder['id']}' in parents "
                                                                   f"and trashed=false"},
                                                             make_if_missing=True)

            await auth_with_the_gargle()

            g_drive = GoogleDrive(gauth)
            for attachment_path in attachment_file_list:
                attachment_name = attachment_path.split("/")[2]
                attachment_drive_object = g_drive.CreateFile(metadata={'title': attachment_name,
                                                                       'parents': [{'id': attachments_folder['id']}]})
                attachment_drive_object.SetContentFile(attachment_path)
                attachment_drive_object.Upload()
                logger.debug(f"Uploaded attachment {attachment_name} to Google Drive.")

            message_log_file = g_drive.CreateFile(metadata={'title': f"{str(target_user.id)}_{current_time}.json",
                                                            'parents': [{'id': cps_bot_folder['id']}]})
            message_log_file.SetContentFile(f"./stored_user_messages/{str(target_user.id)}_{current_time}.json")
            message_log_file.Upload()
            logger.debug(f"Uploaded {str(target_user.id)}_{current_time}.json")

    await ctx.send(f"User: {target_user.display_name} has been warned, found {str(found_messages_count)} messages, "
                   f"handled according to command instructions.", delete_after=delete_messages_after)

    warning_message = f'__**You have been warned by `{ctx.author.display_name}` for: "{reason}"**__\n\n'

    if delete_found_messages:
        warning_message += f'This bot found {str(found_messages_count)} messages sent by you, they have now been ' \
                           f'logged for administrative purposes and deleted from the Discord server. '
    else:
        warning_message += f'This bot found {str(found_messages_count)} messages sent by you, they have now been ' \
                           f'logged for administrative purposes. '

    if should_mute:
        warning_message += f'You have also lost the permission to type in the {ctx.guild.name} Discord server, ' \
                           f'administrators will be in contact soon regarding if/when you will regain this permission.'

    warning_message += f'\n\n**DEPENDING ON THE SEVERITY OF THIS INFRACTION, YOU MAY LOSE ACCESS TO THE DISCORD ' \
                       f'SERVER AND THE OPPORTUNITY TO PARTICIPATE IN SOCIETY ACTIVITIES. SVGE ALSO RESERVES ' \
                       f'THE RIGHT TO REPORT YOUR ACTIONS TO SUSU, THE UNIVERSITY OF SOUTHAMPTON AND DISCORD.**'

    await target_user.send(content=warning_message)

    logger.debug(f"Finished running warn command in {timer() - warn_command_start}s.")


@bot.command
async def get_emote_id(ctx, emote):
    """Returns the ID for a given emote, by name or the emote sent in a message.

    Args:
        - emote: either emote name or object sent in message, if *, command returns a list of all emotes in DMs,
        if *ani, returns a list of all animated emotes."""

    if emote != "*" and emote != "*ani":
        try:
            emoji_object = await commands.EmojiConverter().convert(ctx, emote)
        except commands.CommandError:
            logger.error("Failed to convert target emoji to object.")
            return
        await ctx.send(f"Found emoji `:{emoji_object.name}:` with ID: `{emoji_object.id}`.",
                       delete_after=delete_messages_after)
        return

    emote_list_str = '```{'
    for emoji in ctx.guild.emojis:
        if emoji.guild_id == ctx.guild.id:
            if emoji.animated and emote == "*ani":
                emote_list_str += f"{emoji.name} : {emoji.id},"
            elif (not emoji.animated) and emote == "*":
                emote_list_str += f"{emoji.name} : {emoji.id},"

    emote_list_str = emote_list_str.pop[-1] + "}```"
    await ctx.author.send(f"List of {emote} emotes: \n\n{emote_list_str}", delete_after=delete_messages_after)


@bot.command
async def get_role_id(ctx, *, role: str):
    """Returns the Role ID for a given role.

    Args:
        - role: role name existing in the server of server invocation."""

    try:
        role_obj = await commands.RoleConverter().convert(ctx, role)
    except commands.CommandError:
        logger.error("Failed to convert target role to object.")
        await ctx.send("Failed to convert role to ID.", delete_after=delete_messages_after)
        return

    await ctx.author.send(f"{role_obj.name} | {str(role_obj.id)}")


@bot.command
async def create_react_roles(ctx, *, emote_role_dict: dict):
    """Generates a react message for role allocation

    Args:
        - emote_role_dict: A comma separated dictionary of emote IDs and their associated role IDs"""

    '''
        for keys, values in emote_role_dict.items():
            pass
    '''

    return


@bot.command(pass_context=True)
async def start_vote(ctx, vote_type_new, vote_name, *, candidate_list: str):
    is_admin = False
    for admin_role in admin_role_list:
        if await commands.RoleConverter().convert(ctx, admin_role) in ctx.author.roles:
            is_admin = True
            break

    if not is_admin:
        logger.warning("User: {} attempted to run a vote but doesn't have correct permissions!"
                       .format(ctx.author))
        return

    candidate_list = candidate_list.split(",")

    logger.debug("Successfully finished parsing list of candidates.\n" + str(candidate_list))

    announce_message = f"This is a member only vote for {vote_name}" \
                       f"Below will be the valid candidates for you to vote for, below that the voting format and \n\n" \
                       f"__Eligible Candidates__:\n"

    for candidate in candidate_list:
        announce_message = announce_message+f"- {candidate}\n"

    logger.info("Successfully completed the candidates listed on the announcement message.")

    if vote_type_new:
        announce_message = announce_message + "\nTo vote, send this command to CPSBot in private message: " \
                                              "`{0}vote_for <first_choice> <second_choice> <last_choice>`. " \
                                              "Please understand that while the choice names are not case sensitive, " \
                                              "they __**must be in order and must be spelt the same way, spaces " \
                                              "split up your votes**__.\n\nHere's an example of its use: " \
                                              "`{0}vote_for Freddie Kim_Jong-Un Mao`, here you are voting for " \
                                              "Freddie as your first choice, Lil' Kimmy as your second and Mao as " \
                                              "your last choice.".format(cmd_prefix)

    else:
        announce_message += (
            f'\nTo vote, send the following command to CPSBot in a __**PRIVATE MESSAGE**__:\n'
            f'`{cmd_prefix}vote_for {vote_name} <your_choice>`.\n\nWhile <your_choice> is not case '
            f'sensitive, you should send it exactly the same as in this message to ensure your vote '
            f'is counted and valid. Understand that you may only vote if you have the role: {vote_right_role}.\n\n'
            f'The speeches for each candidate have been sent before this message by Freddie.\n\n'
            f'Your first valid vote will be counted and can not be changed, votes will be made anonymous after an '
            f'initial validation count to ensure democratic integrity, information regarding which way individuals '
            f'have voted will be redacted from the democratic integrity report.'
        )

    vote_storage = {"counts": {}, "votes": {}}

    for candidate in candidate_list:
        vote_storage["counts"][candidate.lower()] = 0

    logger.info("Set up dictionary for holding vote count information.")

    # Now need to handle directories for vote storage under the vote_name
    if not os.path.exists("./active_votes/"):
        os.mkdir("./active_votes/")
        logger.info("Generated directory for active votes.")
    if not os.path.exists("./ended_votes/"):
        os.mkdir("./ended_votes/")
        logger.info("Generated directory for ended votes.")

    if vote_type_new:
        vote_type_str = "freddie_style_vote"
    else:
        vote_type_str = "fpbtp_style_vote"

    with open(f"./active_votes/vote_{vote_name}_{vote_type_str}.json", mode="w") as json_file:
        json.dump(vote_storage, json_file, indent=4)
        logger.info(f"Written JSON file to ./active_votes/vote_{vote_name}_{vote_type_str}.json.")

    target_announce_channel = await commands.TextChannelConverter().convert(ctx, announce_channel_config)

    await target_announce_channel.send(announce_message)


@bot.command(pass_context=True)
async def vote_for(ctx, vote_name, *, votes):
    """Used for special votes configured by bot owner."""

    global vote_file_queue
    global vote_types

    thread_id = random.randint(1, 10000)

    while thread_id in vote_file_queue:
        thread_id = random.randint(1, 10000)

    logging.info("Thread with ID: {} has been opened in a list of length: {}.".format(thread_id, len(vote_file_queue)))

    if not vote_file_queue:
        await vote_file_queue.append(thread_id)
        await asyncio.sleep(0.5)
    else:
        await vote_file_queue.append(thread_id)

    while vote_file_queue[0] != thread_id:
        await asyncio.sleep(0.1)

    if (len(vote_file_queue) - 1) > 0:
        logger.info(f"File queue for votes is currently {len(vote_file_queue)} long.")

    found_vote = False
    for vote_type in vote_types:
        if f"./active_votes/vote_{vote_name}_{vote_type}.json" in os.listdir("./active_votes/"):
            found_vote = True
            break

    if not found_vote:
        logger.debug("User attempted to vote in a vote that does not exist.")
        await ctx.send("The <vote_name> you chose does not exist.")

    #with open()

    vote_file_queue.pop(0)


# Begin logging
print("Logging startup...")
time.sleep(0.1)
if not os.path.exists("./logs/"):
    os.mkdir("./logs/")
logger = logging.getLogger("CPSBot")
logger.setLevel(logging.INFO)
logger_start_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
formatter = logging.Formatter("[{asctime}] [{levelname:}] [{threadName:}] {name}: {message}",
                              "%Y-%m-%d %H:%M:%S", style="{")
file_log = logging.FileHandler(f"./logs/CPSbot{logger_start_time}.log", encoding="utf-8", mode="w")
console_log = logging.StreamHandler()
file_log.setFormatter(formatter)
console_log.setFormatter(formatter)
logger.addHandler(file_log)
logger.addHandler(console_log)
logger.info(f"Configured base in {(timer() - startup_begin):.3f} seconds, running rest of startup.")

if not os.path.exists("./stored_user_messages/"):
    os.mkdir("./stored_user_messages/")
    logger.info("Generated ./stored_user_messages/ directory.")
if not os.path.exists("./carcinogenic_pictures/"):
    os.mkdir("./carcinogenic_pictures/")
    logger.info("Generated ./carcinogenic_pictures/ directory.")

if delete_messages_after == "":
    delete_messages_after = None
else:
    try:
        delete_messages_after = int(delete_messages_after)
    except ValueError:
        logger.error("delete_messages_after variable in config.ini can not be converted to int type.")
        sys.exit("Improper type in config option: delete_messages_after.")

if use_drive_for_backup:
    if not os.path.exists("./configs/credentials.json"):
        with open("./configs/credentials.json", "w") as temp_json:
            pass
    if not os.path.exists("./configs/settings.yaml"):
        yaml_default_struct = {
            "save_credentials": True,
            "get_refresh_token": True,
            "client_config_backend": "file",
            "save_credentials_backend": "file",
            "client_config_file": "./configs/client_secrets.json",
            "save_credentials_file": "./configs/credentials.json",
            "client_config": {
                "client_id": "goes here",
                "client_secret": "goes here"
            },
            "oauth_scope": [
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/drive.metadata"
            ]
        }
        with open("./configs/settings.yaml", "w") as settings_yaml:
            yaml.dump(yaml_default_struct, settings_yaml, default_flow_style=False)
            logger.debug("Made new settings.yaml file.")
    gauth = GoogleAuth(settings_file='./configs/settings.yaml')

bot_beginning_time = timer()
bot.run(bot_token)
