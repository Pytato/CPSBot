import asyncio
import configparser
import json
import logging
import os
import sys
import time
import yaml
import shutil
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

try:
    config.read(os.path.abspath("./configs/config.ini"))
except FileNotFoundError:
    try:
        shutil.copyfile("./configs/default_config.ini", "./configs/config.ini")
        print("You need to set up the config file correctly.")
    except shutil.Error:
        print("Something is wrong with the default config file or the config folder.")
        time.sleep(4)

    sys.exit()

admin_role_names = config["Credentials"]["admin_roles"]
bot_token = config["Credentials"]["bot_token"]
colour_roles = config["Credentials"]["allowed_colour_requesters"]
use_drive_for_backup = config["Credentials"]["use_drive_for_backup"]
owner_id = int(config["Credentials"]["owner_id"])
mute_role_name = config["Misc"]["mute_role_name"]
student_role_name = config["Misc"]["student_role_name"]
exclusion_colours = config["Misc"]["exclusion_colours"]
exclusion_range = config["Misc"]["exclusion_side_length"]
delete_messages_after = config["Misc"]["delete_messages_after"]
listen_channels = config["Misc"]["listen_channels"]
# role_channel_id = config["Misc"]["role_channel_id"]

cmd_prefix = "££"  # COMMAND PREFIX IS HERE FOR EDITING PURPOSES, UNICODE WAS BEING A FUCK SO THAT'S WHY IT'S HERE

admin_role_list = admin_role_names.split(",")
colour_request_list = colour_roles.split(",")
extra_exclusion_colours = exclusion_colours.split(",")
listen_channels_list = listen_channels.split(",")

if admin_role_list[0] == "":
    print("You must specify administrative roles for this bot.")
    sys.exit("No admin roles defined.")

if colour_request_list[0] == "":
    colour_request_list = admin_role_list

if listen_channels_list[0] == "":
    listen_channels_list.pop(0)

if exclusion_range == "":
    exclusion_range = 20
else:
    exclusion_range = int(exclusion_range)

if extra_exclusion_colours[0] == "":
    extra_exclusion_colours = []

if use_drive_for_backup == "True":
    use_drive_for_backup = True
else:
    use_drive_for_backup = False

bot = commands.Bot(command_prefix=cmd_prefix, pm_help=True)

watching = discord.Activity(type=discord.ActivityType.watching, name="you")
check_in_progress = False


async def auth_with_the_gargle():
    global owner_id

    try:
        owner_id = int(owner_id)
        owner_object = await bot.get_user(owner_id)
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


async def clean_colour_roles(context_guild):
    await asyncio.sleep(0.5)
    for role in context_guild.roles:
        if "CPS[0x" in role.name:
            if not role.members:
                await role.delete(reason="Automatic custom colour deletion when unused.")
    logger.debug("Cleaned out empty colour roles")


async def check_colour_users(guild_obj_list):
    while True:
        if len(guild_obj_list) > 1:
            this_guild = guild_obj_list.pop(0)
            await check_colour_users(guild_obj_list)
        else:
            this_guild = guild_obj_list[0]
        parsed_req_list = ""
        for req_role in colour_request_list:
            parsed_req_list += f" - {req_role}\n"
        for role in this_guild.roles:
            if "CPS[0x" in role.name:
                for member_obj in role.members:
                    valid_user = False
                    for mem_role in member_obj.roles:
                        if mem_role.name in colour_request_list:
                            valid_user = True
                            break
                    if valid_user:
                        break
                    else:
                        await member_obj.send(f"Your custom colour role `{role.name}` on {this_guild.name} has been "
                                              f"removed due to you lacking the permissions to retain it. To get a "
                                              f"custom colour, you need one of the following roles:\n"+parsed_req_list)
                        await member_obj.remove_roles(role,
                                                      reason="Automatic colour role removal due to expiry by CPSBot.")
                        logger.info(f"Removed {member_obj.name}'s custom colour role in {this_guild.name}.")

        logger.debug(f"Finished clearing roles for unauthorised users in {this_guild.name}.")

        await clean_colour_roles(this_guild)
        await asyncio.sleep(30)


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
async def on_connect():
    await bot.change_presence(activity=watching)


@bot.event
async def on_ready():
    logger.debug("Start of on_ready()")

    if use_drive_for_backup:
        await auth_with_the_gargle()

    try:
        # noinspection PyUnresolvedReferences,PyUnboundLocalVariable
        colour_cleaner.cancel()
    except NameError:
        pass

    logger.info(f"CPSBot is ready, took {timer() - bot_beginning_time:.3f}s.")

    logger.info("Checking for invalid colour roles.")

    # noinspection PyUnusedLocal
    colour_cleaner = asyncio.create_task(check_colour_users(bot.guilds))


@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    if msg.guild is None:
        return

    message_protected = False
    for protected_address in protected_example_addresses:
        if protected_address in msg.content:
            message_protected = True
            break

    author_obj = msg.author
    author_is_admin = False
    for admin_role in author_obj.roles:
        if admin_role.name in admin_role_list:
            author_is_admin = True

    if not message_protected and not author_is_admin:
        if "@soton.ac.uk" in msg.content:
            await msg.channel.send(f"{msg.author.mention}, Please do not send messages in public channels that "
                                   f"contain your email. If you are attempting to verify with SVGEVerify, use direct "
                                   f"messages and send:\n\n`!email your_email@soton.ac.uk` then follow instructions "
                                   f"sent to your university inbox. \n\nIf you believe your message was deleted in "
                                   f"error, contact <@{str(owner_id)}> with the datetime of your message.",
                                   delete_after=delete_messages_after)
            await msg.author.send("Below is the message this bot has just deleted:\n\n" + msg.content)
            await msg.delete()
            logger.info(f"Auto-deleted message sent by {msg.author.display_name}, in {msg.channel.name}.")
            return

    if listen_channels_list:
        if msg.channel.id not in listen_channels_list:
            return

    if not msg.content.startswith(cmd_prefix):
        return

    logger.info(f'Command sent by "{msg.author.name}#{msg.author.discriminator}": "{msg.content}."')

    try:
        msg_preserved = msg
        await msg.delete()
        await bot.process_commands(msg_preserved)
    except discord.ext.commands.errors.CheckFailure:
        logger.warning(f'User: "{msg.author.name}#{msg.author.discriminator}" issued command "{msg.content}". '
                       f'which failed command checks.')
    except discord.ext.commands.CommandNotFound:
        pass


@bot.command()
@commands.has_any_role(*admin_role_list)
async def shutdown(ctx):
    """Shuts the bot down as gracefully as possible."""
    await ctx.send(":wave:", delete_after=1)
    await asyncio.sleep(3)
    await bot.logout()
    await asyncio.sleep(2)
    sys.exit(0)


@bot.command()
@commands.has_any_role(*admin_role_list)
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


@bot.command()
@commands.has_any_role(*admin_role_list)
async def get_emote_id(ctx, emote):
    """Returns the ID for a given emote, by name or the emote sent in a message.

    Args:
        - emote: either emote name or object sent in message, if *, command returns a list of all emotes in DMs,
        if *ani, returns a list of all animated emotes.
    """

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


'''
@bot.command()
@commands.has_any_role(tuple(admin_role_list))
async def get_role_id(ctx, *, role: str):
    """Returns the Role ID for a given role.

    Args:
        - role: role name existing in the server of invocation.
    """

    try:
        role_obj = await commands.RoleConverter().convert(ctx, role)
    except commands.CommandError:
        logger.error("Failed to convert target role to object.")
        await ctx.send("Failed to convert role to ID.", delete_after=delete_messages_after)
        return

    await ctx.author.send(f"{role_obj.name} | {str(role_obj.id)}", delete_after=delete_messages_after)
'''


# noinspection PyUnboundLocalVariable
@bot.command(name="colourme")
@commands.has_any_role(*colour_request_list)
async def colour_me(ctx, colour_hex: str):
    """Gives the command invoker a custom colour role if they satisfy given conditions.

    If colour_hex is given as remove, the bot will remove the colour role and exit the
    operation.
    """

    # Preprocess the colour
    if colour_hex.lower() == "remove":
        for role in ctx.author.roles:
            if "CPS[0x" in role.name:
                await ctx.author.remove_roles(role, reason="User requested colour role removal.")

        await asyncio.sleep(0.5)
        for role in ctx.guild.roles:
            if "CPS[0x" in role.name:
                if not role.members:
                    await role.delete(reason="Automatic custom colour deletion when unused.")
        return

    if len(colour_hex) > 6:
        await ctx.send("The colour string requested is invalid.", delete_after=delete_messages_after)
        return
    colour_hex_split = [colour_hex[0:2], colour_hex[2:4], colour_hex[4:6]]
    colour_dec_split = []
    for colour in colour_hex_split:
        try:
            colour_dec = int(colour, 16)
        except ValueError:
            return
        if not (0 <= colour_dec <= 255):
            await ctx.message(f"The colour: {colour_hex[0:6]} sits outside of permitted ranges.",
                              delete_after=delete_messages_after)
            return
        colour_dec_split.append(colour_dec)

    exclusion_cube_origins = []

    # Set up exclusion zones for colours
    for admin_role_name in admin_role_list:
        # Let's first gather all the admin role
        try:
            admin_role = await commands.RoleConverter().convert(ctx, admin_role_name)
            # Now find its colour and add it to the list of exclusion origins
            admin_role_colour = admin_role.colour.to_rgb()
            exclusion_cube_origins.append(list(admin_role_colour))
        except discord.ext.commands.errors.BadArgument:
            logger.info("Admin role defined in config not found in guild.")

    for extra_exclusion_colour in extra_exclusion_colours:
        hex_exclusion_colour_split = [extra_exclusion_colour[0:2],
                                      extra_exclusion_colour[2:4],
                                      extra_exclusion_colour[4:6]]
        exclusion_colour_dec = []
        for colour in hex_exclusion_colour_split:
            exclusion_colour_dec.append(int(colour, 16))
        exclusion_cube_origins.append(exclusion_colour_dec)

    # Now we have all of the required cube origins, time to check our colour against each.
    for cube_center in exclusion_cube_origins:
        in_cube = True
        for i in range(3):
            dim_min_max = [cube_center[i] - exclusion_range, cube_center[i] + exclusion_range]
            if not (dim_min_max[0] < colour_dec_split[i] < dim_min_max[1]):
                in_cube = False
                break
        if colour_dec == cube_center:
            in_cube = True
        if in_cube:
            await ctx.send(f"The colour you have selected is too close to that of an admin role or "
                           f"protected colour.",
                           delete_after=delete_messages_after)
            return

    # Not much left to do, only need to create the custom colour role and make sure that it
    # sits below the lowest defined admin role.
    admin_role_obj_list = {}
    for admin_role in admin_role_list:
        try:
            admin_role_object = await commands.RoleConverter().convert(ctx, admin_role)
            admin_role_obj_list[admin_role_object.position] = admin_role_object
        except discord.ext.commands.errors.BadArgument:
            logger.info("Admin role defined in config not found in guild.")

    sorted_admin_list_pos = sorted(admin_role_obj_list)

    # Now we have the sorted list of admin roles, let's query all roles and see if we already have
    # the requested colour created. CPSBot colour roles have the naming convention: CPS[0x<R><G><B>] in hex.
    try:
        prev_colour = await commands.RoleConverter().convert(ctx, f"CPS[0x{colour_hex.upper()}]")
        await prev_colour.edit(position=sorted_admin_list_pos[0])
        await ctx.author.add_roles(prev_colour, reason="Custom colour requested by DLC Member.")
        return
    except commands.BadArgument:
        # The role doesn't already exist, let's pass.
        pass

    # Now to create the role we wanted all along.
    new_colour_role = await ctx.guild.create_role(name=f"CPS[0x{colour_hex.upper()}]",
                                                  reason="Custom colour role generation by CPSBot.",
                                                  colour=discord.Colour.from_rgb(r=colour_dec_split[0],
                                                                                 g=colour_dec_split[1],
                                                                                 b=colour_dec_split[2]))

    await new_colour_role.edit(position=sorted_admin_list_pos[0])
    await new_colour_role.edit(position=sorted_admin_list_pos[0])

    for invoker_role in ctx.author.roles:
        if "CPS[0x" in invoker_role.name:
            await ctx.author.remove_roles(invoker_role, reason="Removing old colour role from user.")

    await ctx.author.add_roles(new_colour_role, reason="Automatic custom colour allocation by request.")

    await clean_colour_roles(ctx.guild)


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
