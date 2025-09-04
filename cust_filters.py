import re
from typing import Optional

import telegram
from telegram import ParseMode, InlineKeyboardMarkup, Message, Chat, InlineKeyboardButton
from telegram import Update, Bot
from telegram.error import BadRequest
from telegram.ext import CommandHandler, MessageHandler, DispatcherHandlerStop, CallbackQueryHandler, run_async
from telegram.utils.helpers import escape_markdown

from tg_bot import dispatcher, LOGGER
from tg_bot.modules.disable import DisableAbleCommandHandler
from tg_bot.modules.helper_funcs.chat_status import user_admin
from tg_bot.modules.helper_funcs.extraction import extract_text
from tg_bot.modules.helper_funcs.filters import CustomFilters
from tg_bot.modules.helper_funcs.misc import build_keyboard
from tg_bot.modules.helper_funcs.string_handling import split_quotes, button_markdown_parser
from tg_bot.modules.sql import cust_filters_sql as sql

from tg_bot.modules.connection import connected

HANDLER_GROUP = 10
BASIC_FILTER_STRING = "*Filters in this chat:*\n"


@run_async
def list_handlers(bot: Bot, update: Update, args=None):
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]

    conn = connected(bot, update, chat, user.id, need_admin=False)
    if not conn == False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
        filter_list = "*Filters in {}:*\n"
    else:
        chat_id = update.effective_chat.id
        if chat.type == "private":
            chat_name = "local filters"
            filter_list = "*local filters:*\n"
        else:
            chat_name = chat.title
            filter_list = "*Filters in {}*:\n"

    # Get page number from args, default to 0
    page = 0
    if args and len(args) > 0:
        try:
            page = int(args[0]) - 1  # Convert to 0-based index
            if page < 0:
                page = 0
        except ValueError:
            page = 0

    all_handlers = sql.get_chat_triggers(chat_id)

    if not all_handlers:
        update.effective_message.reply_text("No filters in {}!".format(chat_name))
        return

    # Pagination settings
    items_per_page = 10
    total_pages = (len(all_handlers) + items_per_page - 1) // items_per_page
    
    # Ensure page is within bounds
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0

    # Get items for current page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(all_handlers))
    page_handlers = all_handlers[start_idx:end_idx]

    # Build the message
    filter_list = f"*Filters in {chat_name} (Page {page+1}/{total_pages}):*\n"
    for i, keyword in enumerate(page_handlers, start=1):
        filter_list += f"{start_idx + i}. {escape_markdown(keyword)}\n"

    # Build navigation buttons
    buttons = []
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"filters_prev_{chat_id}_{page}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"filters_next_{chat_id}_{page}"))
        buttons.append(nav_buttons)

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    update.effective_message.reply_text(filter_list, parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=keyboard)

@run_async
def filters_callback(bot: Bot, update: Update):
    query = update.callback_query
    user = update.effective_user
    data = query.data.split('_')
    
    if len(data) < 4:
        query.answer("Invalid callback data.")
        return
        
    action = data[1]
    chat_id = int(data[2])
    current_page = int(data[3])
    
    # Check if user has permission to view filters
    from tg_bot.modules.helper_funcs.chat_status import is_user_admin
    if not is_user_admin(update.effective_chat, user.id):
        query.answer("You need to be an admin to view filters.")
        return

    # Calculate new page
    if action == "prev":
        new_page = current_page - 1
    elif action == "next":
        new_page = current_page + 1
    else:
        query.answer("Invalid action.")
        return

    all_handlers = sql.get_chat_triggers(chat_id)

    if not all_handlers:
        query.edit_message_text("No filters in this chat!")
        return

    # Pagination settings
    items_per_page = 10
    total_pages = (len(all_handlers) + items_per_page - 1) // items_per_page
    
    # Ensure page is within bounds
    if new_page >= total_pages:
        new_page = total_pages - 1
    if new_page < 0:
        new_page = 0

    # Get items for current page
    start_idx = new_page * items_per_page
    end_idx = min(start_idx + items_per_page, len(all_handlers))
    page_handlers = all_handlers[start_idx:end_idx]

    # Build the message
    chat_name = dispatcher.bot.getChat(chat_id).title
    filter_list = f"*Filters in {chat_name} (Page {new_page+1}/{total_pages}):*\n"
    for i, keyword in enumerate(page_handlers, start=1):
        filter_list += f"{start_idx + i}. {escape_markdown(keyword)}\n"

    # Build navigation buttons
    buttons = []
    if total_pages > 1:
        nav_buttons = []
        if new_page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"filters_prev_{chat_id}_{new_page}"))
        if new_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"filters_next_{chat_id}_{new_page}"))
        buttons.append(nav_buttons)

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    try:
        query.edit_message_text(text=filter_list, parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=keyboard)
        query.answer()
    except Exception as e:
        LOGGER.exception("Error in filters pagination: %s", str(e))
        query.answer("Error updating filters list.")


# NOT ASYNC BECAUSE DISPATCHER HANDLER RAISED
@user_admin
def filters(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    msg = update.effective_message  # type: Optional[Message]
    args = msg.text.split(None, 1)  # use python's maxsplit to separate Cmd, keyword, and reply_text

    conn = connected(bot, update, chat, user.id)
    if not conn == False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        chat_id = update.effective_chat.id
        if chat.type == "priv    if len(args) < 2:
        return

    extracted = split_quotes(args[1])
    if len(extracted) < 1:
        return
    # set trigger -> lower, so as to avoid adding duplicate filters with different cases
    keyword = extracted[0].lower()

    is_sticker = False
    is_document = False
    is_image = False
    is_voice = False
    is_audio = False
    is_video = False
    buttons = []

    # determine what the contents of the filter are - text, image, sticker, etc
    if len(extracted) >= 2:
        offset = len(extracted[1]) - len(msg.text)  # set correct offset relative to command + notename
        content, buttons = button_markdown_parser(extracted[1], entities=msg.parse_entities(), offset=offset)
        content = content.strip()
        if not content:
            msg.reply_text("There is no note message - You can't JUST have buttons, you need a message to go with it!")
            return

    elif msg.reply_to_message and msg.reply_to_message.sticker:
        content = msg.reply_to_message.sticker.file_id
        is_sticker = True

    elif msg.reply_to_message and msg.reply_to_message.document:
        content = msg.reply_to_message.document.file_id
        is_document = True

    elif msg.reply_to_message and msg.reply_to_message.photo:
        offset = len(msg.reply_to_message.caption)
        ignore_underscore_case, buttons = button_markdown_parser(msg.reply_to_message.caption, entities=msg.reply_to_message.parse_entities(), offset=offset)
        content = msg.reply_to_message.photo[-1].file_id  # last elem = best quality
        is_image = True

    elif msg.reply_to_message and msg.reply_to_message.audio:
        content = msg.reply_to_message.audio.file_id
        is_audio = True

    elif msg.reply_to_message and msg.reply_to_message.voice:
        content = msg.reply_to_message.voice.file_id
        is_voice = True

    elif msg.reply_to_message and msg.reply_to_message.video:
        content = msg.reply_to_message.video.file_id
        is_video = True

    else:
        msg.reply_text("You didn't specify what to reply with!")
        return

    # Add the filter
    # Note: perhaps handlers can be removed somehow using sql.get_chat_filters
    for handler in dispatcher.handlers.get(HANDLER_GROUP, []):
        if handler.filters == (keyword, chat.id):
            dispatcher.remove_handler(handler, HANDLER_GROUP)

    sql.add_filter(chat_id, keyword, content, is_sticker, is_document, is_image, is_audio, is_voice, is_video,
                   buttons)

    msg.reply_text("Handler '{}' added in *{}*!".format(keyword, chat_name), parse_mode=telegram.ParseMode.MARKDOWN)
    raise DispatcherHandlerStop


# NOT ASYNC BECAUSE DISPATCHER HANDLER RAISED
@user_admin
def stop_filter(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    args = update.effective_message.text.split(None, 1)

    conn = connected(bot, update, chat, user.id)
    if not conn == False:
        chat_id = conn
        chat_name = dispatcher.bot.getChat(conn).title
    else:
        chat_id = chat.id
        if chat.type == "private":
            chat_name = "local notes"
        else:
            chat_name = chat.title

    if len(args) < 2:
        return

    chat_filters = sql.get_chat_triggers(chat_id)

    if not chat_filters:
        update.effective_message.reply_text("No filters are active here!")
        return

    for keyword in chat_filters:
        if keyword == args[1]:
            sql.remove_filter(chat_id, args[1])
            update.effective_message.reply_text("Yep, I'll stop replying to that in *{}*.".format(chat_name), parse_mode=telegram.ParseMode.MARKDOWN)
            raise DispatcherHandlerStop

    update.effective_message.reply_text("That's not a current filter - run /filters for all active filters.")


@run_async
def reply_filter(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]
    message = update.effective_message  # type: Optional[Message]
    to_match = extract_text(message)
    if not to_match:
        return

    # my custom thing
    if message.reply_to_message:
        message = message.reply_to_message
    ad_filter = ""
    # my custom thing

    chat_filters = sql.get_chat_triggers(chat.id)
    for keyword in chat_filters:
        pattern = r"( |^|[^\w])" + re.escape(keyword) + r"( |$|[^\w])"
        if re.search(pattern, to_match, flags=re.IGNORECASE):
            filt = sql.get_filter(chat.id, keyword)
            buttons = sql.get_buttons(chat.id, filt.keyword)
            if filt.is_sticker:
                message.reply_sticker(filt.reply)
            elif filt.is_document:
                message.reply_document(filt.reply)
            elif filt.is_image:
                if len(buttons) > 0:
                    keyb = build_keyboard(buttons)
                    keyboard = InlineKeyboardMarkup(keyb)
                    message.reply_photo(filt.reply, reply_markup=keyboard)
                else:
                    message.reply_photo(filt.reply)
            elif filt.is_audio:
                message.reply_audio(filt.reply)
            elif filt.is_voice:
                message.reply_voice(filt.reply)
            elif filt.is_video:
                message.reply_video(filt.reply)
            elif filt.has_markdown:
                keyb = build_keyboard(buttons)
                keyboard = InlineKeyboardMarkup(keyb)

                should_preview_disabled = True
                if "telegra.ph" in filt.reply or "youtu.be" in filt.reply:
                    should_preview_disabled = False

                try:
                    message.reply_text(ad_filter + "\n" + filt.reply, parse_mode=ParseMode.MARKDOWN,
                                       disable_web_page_preview=should_preview_disabled,
                                       reply_markup=keyboard)
                except BadRequest as excp:
                    if excp.message == "Unsupported url protocol":
                        message.reply_text("You seem to be trying to use an unsupported url protocol. Telegram "
                                           "doesn't support buttons for some protocols, such as tg://. Please try "
                                           "again, or ask in @MarieSupport for help.")
                    elif excp.message == "Reply message not found":
                        bot.send_message(chat.id, filt.reply, parse_mode=ParseMode.MARKDOWN,
                                         disable_web_page_preview=True,
                                         reply_markup=keyboard)
                    else:
                        message.reply_text("This note could not be sent, as it is incorrectly formatted. Ask in "
                                           "@MarieSupport if you can't figure out why!")
                        LOGGER.warning("Message %s could not be parsed", str(filt.reply))
                        LOGGER.exception("Could not parse filter %s in chat %s", str(filt.keyword), str(chat.id))

            else:
                # LEGACY - all new filters will have has_markdown set to True.
                message.reply_text(ad_filter + "\n" + filt.reply)
            break


def __stats__():
    return "{} filters, across {} chats.".format(sql.num_filters(), sql.num_chats())


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    cust_filters = sql.get_chat_triggers(chat_id)
    return "There are `{}` custom filters here.".format(len(cust_filters))

FILTERS_CALLBACK_HANDLER = CallbackQueryHandler(filters_callback, pattern=r"filters_")
dispatcher.add_handler(FILTERS_CALLBACK_HANDLER)

__help__ = """
 - /filters: list all active filters in this chat. Use /filters <page> to view specific pages.

*Admin only:*
 - /filter <keyword> <reply message>: add a filter to this chat. The bot will now reply that message whenever 'keyword'\
is mentioned. If you reply to a sticker with a keyword, the bot will reply with that sticker. NOTE: all filter \
keywords are in lowercase. If you want your keyword to be a sentence, use quotes. eg: /filter "hey there" How you \
doin?
 - /stop <filter keyword>: stop that filter.
"""

__mod_name__ = "Filters"

FILTER_HANDLER = CommandHandler("filter", filters)
STOP_HANDLER = CommandHandler("stop", stop_filter)
LIST_HANDLER = DisableAbleCommandHandler("filters", list_handlers, pass_args=True, admin_ok=True)
CUST_FILTER_HANDLER = MessageHandler(CustomFilters.has_text, reply_filter, edited_updates=True)

dispatcher.add_handler(FILTER_HANDLER)
dispatcher.add_handler(STOP_HANDLER)
dispatcher.add_handler(LIST_HANDLER)
dispatcher.add_handler(CUST_FILTER_HANDLER, HANDLER_GROUP)
