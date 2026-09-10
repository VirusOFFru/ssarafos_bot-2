import logging
from typing import Final

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import database as db
from config import BOT_TOKEN, ADMIN_ID, SUPPORT_USERNAME
from keyboards import (
    main_menu,
    admin_menu,
    catalog_keyboard,
    product_keyboard,
    cart_keyboard,
    confirm_order_keyboard,
    order_manage_keyboard,
    user_order_keyboard,
    products_manage_keyboard,
    single_product_manage_keyboard,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
ADD_PRODUCT_NAME: Final = 10
ADD_PRODUCT_DESC: Final = 11
ADD_PRODUCT_PRICE: Final = 12
ADD_PRODUCT_PHOTO: Final = 13
ADD_PRODUCT_COLLECTION: Final = 14

CHECKOUT_ADDRESS: Final = 1
CHECKOUT_COMMENT: Final = 2
CHECKOUT_CONFIRM: Final = 3

ADD_TRACK: Final = 20

# Delivery cost constant
DELIVERY_COST: Final = 389


# ─── Utility Functions ─────────────────────────────────────────────────────────


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def format_cart(items) -> tuple[str, int, int]:
    """
    Возвращает (текст корзины, общая сумма товаров, количество товаров)
    """
    lines = ["🛒 Ваша корзина:\n"]
    subtotal = 0
    total_quantity = 0
    
    for item in items:
        item_total = item["price"] * item["quantity"]
        subtotal += item_total
        total_quantity += item["quantity"]
        lines.append(f"• {item['name']} — {item['quantity']} шт. × {item['price']} ₽ = {item_total} ₽")
    
    lines.append(f"\n💰 Сумма товаров: {subtotal} ₽")
    return "\n".join(lines), subtotal, total_quantity


def calculate_order_total(subtotal: int, total_quantity: int) -> tuple[int, int, int]:
    """
    Рассчитывает финальную сумму заказа с учётом доставки и скидок.
    Возвращает (итого, стоимость доставки, скидка в процентах)
    """
    delivery = 0 if total_quantity >= 2 else DELIVERY_COST
    discount_pct = 10 if total_quantity >= 3 else 0
    
    if discount_pct > 0:
        discount_amount = int(subtotal * discount_pct / 100)
        subtotal -= discount_amount
    
    total = subtotal + delivery
    return total, delivery, discount_pct


# ─── User Handlers ─────────────────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        text = f"Привет, {user.first_name}! Ты администратор 👑\nВыбери действие:"
        await update.message.reply_text(text, reply_markup=admin_menu())
    else:
        text = f"Привет, {user.first_name}! 👋\nДобро пожаловать в магазин брелоков ssarafos\n\nВыберите нужный раздел:"
        await update.message.reply_text(text, reply_markup=main_menu())


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text("Главное меню администратора", reply_markup=admin_menu())
    else:
        await update.message.reply_text("Главное меню", reply_markup=main_menu())


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    products = await db.get_all_products()
    if not products:
        await update.message.reply_text("Каталог пока пуст 📦", reply_markup=main_menu())
        return

    await update.message.reply_text(
        "🛍 Каталог товаров:\nВыберите товар для подробностей",
        reply_markup=catalog_keyboard(products),
    )


async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[1])
    product = await db.get_product(product_id)

    if not product:
        await query.edit_message_text("Товар не найден 😢")
        return

    text = (
        f"📦 {product['name']}\n\n"
        f"{product['description']}\n\n"
        f"💰 Цена: {product['price']} ₽\n"
    )
    if product["collection_name"]:
        text += f"🏷 Коллекция: {product['collection_name']}\n"

    if product["photo_id"]:
        await query.message.reply_photo(
            photo=product["photo_id"],
            caption=text,
            reply_markup=product_keyboard(product_id),
        )
        await query.message.delete()
    else:
        await query.edit_message_text(text, reply_markup=product_keyboard(product_id))


async def catalog_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    products = await db.get_all_products()
    await query.edit_message_text(
        "🛍 Каталог товаров:\nВыберите товар для подробностей",
        reply_markup=catalog_keyboard(products),
    )


async def cart_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Добавлено в корзину ✅")

    product_id = int(query.data.split(":")[2])
    user_id = query.from_user.id

    await db.add_to_cart(user_id, product_id)


async def cart_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    items = await db.get_cart(user_id)

    if not items:
        await update.message.reply_text("Ваша корзина пуста 🛒", reply_markup=main_menu())
        return

    text, subtotal, total_quantity = format_cart(items)
    total, delivery, discount_pct = calculate_order_total(subtotal, total_quantity)
    
    if delivery > 0:
        text += f"🚚 Доставка: {delivery} ₽\n"
    else:
        text += "🚚 Доставка: бесплатно 🎉\n"
    
    if discount_pct > 0:
        text += f"🎁 Скидка {discount_pct}%: уже применена\n"
    
    text += f"\n✅ Итого: {total} ₽"

    await update.message.reply_text(text, reply_markup=cart_keyboard(items, total_quantity))


async def cart_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Убрано из корзины ✅")

    cart_item_id = int(query.data.split(":")[2])
    user_id = query.from_user.id

    await db.remove_from_cart(cart_item_id)

    items = await db.get_cart(user_id)
    if not items:
        await query.edit_message_text("Ваша корзина пуста 🛒")
        return

    text, subtotal, total_quantity = format_cart(items)
    total, delivery, discount_pct = calculate_order_total(subtotal, total_quantity)
    
    if delivery > 0:
        text += f"🚚 Доставка: {delivery} ₽\n"
    else:
        text += "🚚 Доставка: бесплатно 🎉\n"
    
    if discount_pct > 0:
        text += f"🎁 Скидка {discount_pct}%: уже применена\n"
    
    text += f"\n✅ Итого: {total} ₽"

    await query.edit_message_text(text, reply_markup=cart_keyboard(items, total_quantity))


async def cart_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Корзина очищена ✅")

    user_id = query.from_user.id
    await db.clear_cart(user_id)
    await query.edit_message_text("Корзина очищена 🛒")


async def delivery_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback для кнопки подсказки о доставке"""
    query = update.callback_query
    await query.answer(
        "От 2 брелоков доставка бесплатно! От 3 брелоков — скидка 10% на весь заказ 🎉",
        show_alert=True
    )


# ─── Checkout Flow ─────────────────────────────────────────────────────────────


async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    items = await db.get_cart(user_id)

    if not items:
        await query.edit_message_text("Ваша корзина пуста 🛒")
        return ConversationHandler.END

    context.user_data["checkout_items"] = [dict(item) for item in items]

    await query.edit_message_text(
        "📍 Укажите адрес доставки:\n\n"
        "Пример: г. Москва, ул. Ленина 10, кв. 5"
    )
    return CHECKOUT_ADDRESS


async def checkout_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    address = update.message.text.strip()

    if len(address) < 10:
        await update.message.reply_text("Адрес слишком короткий. Укажите полный адрес доставки:")
        return CHECKOUT_ADDRESS

    context.user_data["checkout_address"] = address

    await update.message.reply_text(
        "💬 Желаете добавить комментарий к заказу?\n\n"
        "«нет» / «пропустить» чтобы продолжить без комментария."
    )
    return CHECKOUT_COMMENT


async def checkout_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment_text = update.message.text.strip()
    
    # Если пользователь отказался от комментария
    if comment_text.lower() in ["нет", "пропустить", "skip", "no", "-"]:
        comment_text = ""
    
    context.user_data["checkout_comment"] = comment_text

    items = context.user_data.get("checkout_items", [])
    address = context.user_data.get("checkout_address", "")

    text, subtotal, total_quantity = format_cart(items)
    total, delivery, discount_pct = calculate_order_total(subtotal, total_quantity)

    confirmation = f"{text}\n\n"
    
    if delivery > 0:
        confirmation += f"🚚 Доставка: {delivery} ₽\n"
    else:
        confirmation += "🚚 Доставка: бесплатно 🎉\n"
    
    if discount_pct > 0:
        confirmation += f"🎁 Скидка {discount_pct}%: уже применена\n"
    
    confirmation += f"\n✅ Итого к оплате: {total} ₽\n\n"
    confirmation += f"📍 Адрес: {address}\n"
    
    if comment_text:
        confirmation += f"💬 Комментарий: {comment_text}\n"

    confirmation += "\n🎀Всё верно?"

    context.user_data["checkout_total"] = total
    context.user_data["checkout_delivery"] = delivery

    await update.message.reply_text(confirmation, reply_markup=confirm_order_keyboard())
    return CHECKOUT_CONFIRM


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user = query.from_user
    items = context.user_data.get("checkout_items", [])
    address = context.user_data.get("checkout_address", "")
    comment = context.user_data.get("checkout_comment", "")
    total = context.user_data.get("checkout_total", 0)
    delivery = context.user_data.get("checkout_delivery", 0)

    if not items:
        await query.edit_message_text("Ошибка: корзина пуста")
        return ConversationHandler.END

    username = user.username or ""
    full_name = user.full_name or ""

    order_id = await db.create_order(
        user_id=user.id,
        username=username,
        full_name=full_name,
        address=address,
        comment=comment,
        total=total,
        delivery_cost=delivery,
        items=items,
    )

    await db.clear_cart(user.id)

    await query.edit_message_text(
        f"✅ Заказ #{order_id} создан!\n\n"
        f"Спасибо за покупку! Мы свяжемся с Вами в ближайшее время для подтверждения.\n\n"
        f"Отслеживай статус заказа в разделе «📦 Мои заказы»"
    )

    # Notify admin
    admin_text = (
        f"🔔 Новый заказ #{order_id}\n\n"
        f"👤 От: {full_name} (@{username if username else 'без username'})\n"
        f"💰 Сумма: {total} ₽\n"
        f"📍 Адрес: {address}\n"
    )
    if comment:
        admin_text += f"💬 Комментарий: {comment}\n"
    
    admin_text += "\nСостав заказа:\n"
    for item in items:
        admin_text += f"• {item['name']} — {item['quantity']} шт. × {item['price']} ₽\n"

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_text,
        reply_markup=order_manage_keyboard(order_id, "new"),
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data.clear()

    await query.edit_message_text("❌ Оформление заказа отменено")
    return ConversationHandler.END


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    orders = await db.get_user_orders(user_id)

    if not orders:
        await update.message.reply_text("У Вас пока нет заказов 📦", reply_markup=main_menu())
        return

    # Группируем заказы по статусам
    current_orders = []
    history_orders = []

    for order in orders:
        if order["status"] in {"new", "shipped"}:
            current_orders.append(order)
        else:
            history_orders.append(order)

    STATUS_EMOJI = {
        "new": "🆕",
        "shipped": "🚚",
        "delivered": "✅",
        "cancelled": "❌",
    }

    STATUS_TEXT = {
        "new": "Новый",
        "shipped": "В пути",
        "delivered": "Доставлен",
        "cancelled": "Отменён",
    }

    text = "📦 Твои заказы:\n\n"

    if current_orders:
        text += "🔵 Текущие заказы:\n"
        for order in current_orders:
            emoji = STATUS_EMOJI.get(order["status"], "❓")
            status = STATUS_TEXT.get(order["status"], order["status"])
            text += f"\n{emoji} Заказ #{order['id']} — {status}\n"
            text += f"💰 Сумма: {order['total']} ₽\n"
            if order["track_number"]:
                text += f"   🔍 Трек: {order['track_number']}\n"

    if history_orders:
        text += "\n\n📋 История заказов:\n"
        for order in history_orders:
            emoji = STATUS_EMOJI.get(order["status"], "❓")
            status = STATUS_TEXT.get(order["status"], order["status"])
            text += f"\n{emoji} Заказ #{order['id']} — {status}\n"
            text += f"💰 Сумма: {order['total']} ₽\n"

    await update.message.reply_text(text, reply_markup=main_menu())


async def user_order_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пользователь отмечает что получил заказ"""
    query = update.callback_query
    await query.answer("Спасибо за подтверждение! 🎉")

    order_id = int(query.data.split(":")[2])
    await db.update_order_status(order_id, "delivered")

    await query.edit_message_text(
        f"✅ Заказ #{order_id} отмечен как доставленный!\n\n"
        "Спасибо за покупку! Будем рады видеть Вас снова 😊"
    )

    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"✅ Пользователь подтвердил получение заказа #{order_id}"
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"📞 Поддержка\n\nПо всем вопросам пишите: @{SUPPORT_USERNAME}",
        reply_markup=main_menu(),
    )


# ─── Admin Handlers ────────────────────────────────────────────────────────────


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return

    orders = await db.get_all_orders(limit=20)
    if not orders:
        await update.message.reply_text("Заказов пока нет 📦", reply_markup=admin_menu())
        return

    STATUS_EMOJI = {
        "new": "🆕",
        "shipped": "🚚",
        "delivered": "✅",
        "cancelled": "❌",
    }

    STATUS_TEXT = {
        "new": "Новый",
        "shipped": "В пути",
        "delivered": "Доставлен",
        "cancelled": "Отменён",
    }

    text = "📋 Последние заказы:\n\n"
    for order in orders:
        emoji = STATUS_EMOJI.get(order["status"], "❓")
        status = STATUS_TEXT.get(order["status"], order["status"])
        text += (
            f"{emoji} Заказ #{order['id']} — {status}\n"
            f"   👤 {order['full_name']} (@{order['username'] if order['username'] else 'нет'})\n"
            f"   💰 {order['total']} ₽\n"
        )
        if order["track_number"]:
            text += f"   🔍 {order['track_number']}\n"
        text += "\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📦 Заказ #{o['id']}", callback_data=f"admin:view_order:{o['id']}")]
        for o in orders[:10]
    ])

    await update.message.reply_text(text, reply_markup=keyboard)


async def admin_view_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[2])
    order = await db.get_order(order_id)
    items = await db.get_order_items(order_id)

    if not order:
        await query.edit_message_text("Заказ не найден")
        return

    STATUS_TEXT = {
        "new": "🆕 Новый",
        "shipped": "🚚 В пути",
        "delivered": "✅ Доставлен",
        "cancelled": "❌ Отменён",
    }

    text = (
        f"📦 Заказ #{order['id']}\n\n"
        f"Статус: {STATUS_TEXT.get(order['status'], order['status'])}\n"
        f"👤 {order['full_name']} (@{order['username'] if order['username'] else 'нет'})\n"
        f"📍 {order['address']}\n"
    )
    
    if order["comment"]:
        text += f"💬 Комментарий: {order['comment']}\n"
    
    text += f"💰 Сумма: {order['total']} ₽\n"
    
    if order["delivery_cost"] > 0:
        text += f"🚚 Доставка: {order['delivery_cost']} ₽\n"
    else:
        text += "🚚 Доставка: бесплатно\n"
    
    if order["track_number"]:
        text += f"🔍 Трек: {order['track_number']}\n"
    
    text += f"\nДата: {order['created_at']}\n\n"
    text += "Состав заказа:\n"
    
    for item in items:
        text += f"• {item['product_name']} — {item['quantity']} шт. × {item['price']} ₽\n"

    await query.edit_message_text(text, reply_markup=order_manage_keyboard(order_id, order["status"]))


async def admin_order_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ отмечает заказ как доставленный"""
    query = update.callback_query
    await query.answer("Заказ отмечен доставленным ✅")

    if not is_admin(query.from_user.id):
        return

    order_id = int(query.data.split(":")[2])
    await db.update_order_status(order_id, "delivered")

    order = await db.get_order(order_id)
    await query.message.edit_reply_markup(reply_markup=order_manage_keyboard(order_id, "delivered"))

    # Notify user
    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"✅ Ваш заказ #{order_id} доставлен!\n\nСпасибо за покупку! Будем рады видеть Вас снова 😊"
    )


async def admin_order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Заказ отменён ❌")

    if not is_admin(query.from_user.id):
        return

    order_id = int(query.data.split(":")[2])
    await db.update_order_status(order_id, "cancelled")

    order = await db.get_order(order_id)
    await query.message.edit_reply_markup(reply_markup=order_manage_keyboard(order_id, "cancelled"))

    # Notify user
    await context.bot.send_message(
        chat_id=order["user_id"],
        text=f"❌ Ваш заказ #{order_id} отменён.\n\nПо вопросам обращайся в поддержку: @{SUPPORT_USERNAME}"
    )


# ─── Add Track Number ──────────────────────────────────────────────────────────


async def admin_track_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    order_id = int(query.data.split(":")[2])
    context.user_data["track_order_id"] = order_id

    await query.edit_message_text(
        f"🚚 Введите трек-номер для заказа #{order_id}:\n\n"
        "После этого статус заказа автоматически изменится на «В пути»"
    )
    return ADD_TRACK


async def admin_track_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    track_number = update.message.text.strip()
    order_id = context.user_data.get("track_order_id")

    if not order_id:
        await update.message.reply_text("Ошибка: заказ не найден")
        return ConversationHandler.END

    await db.update_track_number(order_id, track_number)

    order = await db.get_order(order_id)

    await update.message.reply_text(
        f"✅ Трек-номер добавлен!\n\n"
        f"Заказ #{order_id} переведён в статус «В пути»",
        reply_markup=admin_menu(),
    )

    # Notify user
    await context.bot.send_message(
        chat_id=order["user_id"],
        text=(
            f"🚚 Ваш заказ #{order_id} отправлен!\n\n"
            f"Трек-номер: {track_number}\n\n"
            "Отслеживайте статус в разделе «📦 Мои заказы»"
        ),
        reply_markup=user_order_keyboard(order_id, "shipped")
    )

    context.user_data.pop("track_order_id", None)
    return ConversationHandler.END


async def admin_track_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Добавление трек-номера отменено", reply_markup=admin_menu())
    context.user_data.pop("track_order_id", None)
    return ConversationHandler.END


# ─── Add Product ───────────────────────────────────────────────────────────────


async def admin_add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return ConversationHandler.END

    await update.message.reply_text("📦 Добавление товара\n\n1️⃣ Введите название товара:")
    return ADD_PRODUCT_NAME


async def admin_add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["product_name"] = update.message.text.strip()
    await update.message.reply_text("2️⃣ Введите описание товара:")
    return ADD_PRODUCT_DESC


async def admin_add_product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["product_desc"] = update.message.text.strip()
    await update.message.reply_text("3️⃣ Введите цену (только число, например 1500):")
    return ADD_PRODUCT_PRICE


async def admin_add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = int(update.message.text.strip())
        context.user_data["product_price"] = price
        await update.message.reply_text(
            "4️⃣ Отправьте фото товара или напишите «нет» чтобы пропустить:"
        )
        return ADD_PRODUCT_PHOTO
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число. Попробуйте ещё раз:")
        return ADD_PRODUCT_PRICE


async def admin_add_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        context.user_data["product_photo"] = photo_id
    elif update.message.text and update.message.text.strip().lower() in ["нет", "skip", "пропустить", "-"]:
        context.user_data["product_photo"] = None
    else:
        await update.message.reply_text("Отправьте фото или напишите «нет»:")
        return ADD_PRODUCT_PHOTO

    await update.message.reply_text("5️⃣ Введите название коллекции или напиши «нет»:")
    return ADD_PRODUCT_COLLECTION


async def admin_add_product_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    collection = update.message.text.strip()
    if collection.lower() in ["нет", "skip", "пропустить", "-"]:
        collection = ""

    context.user_data["product_collection"] = collection

    name = context.user_data.get("product_name", "")
    desc = context.user_data.get("product_desc", "")
    price = context.user_data.get("product_price", 0)
    photo = context.user_data.get("product_photo")

    await db.add_product(name, desc, price, photo, collection)

    await update.message.reply_text(
        f"✅ Товар «{name}» добавлен в каталог!",
        reply_markup=admin_menu(),
    )

    context.user_data.clear()
    return ConversationHandler.END


async def admin_add_product_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Добавление товара отменено", reply_markup=admin_menu())
    context.user_data.clear()
    return ConversationHandler.END


# ─── Manage Products ───────────────────────────────────────────────────────────


async def admin_manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return

    products = await db.get_all_products(include_hidden=True)
    if not products:
        await update.message.reply_text("Товаров пока нет 📦", reply_markup=admin_menu())
        return

    await update.message.reply_text(
        "📦 Управление товарами:\n\n✅ — В продаже\n❌ — Снят с продажи",
        reply_markup=products_manage_keyboard(products),
    )


async def admin_product_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[2])
    product = await db.get_product(product_id)

    if not product:
        await query.edit_message_text("Товар не найден")
        return

    status = "✅ В продаже" if product["in_stock"] else "❌ Снят с продажи"
    text = (
        f"📦 {product['name']}\n\n"
        f"Статус: {status}\n"
        f"💰 Цена: {product['price']} ₽\n"
    )
    if product["collection_name"]:
        text += f"🏷 Коллекция: {product['collection_name']}\n"

    await query.edit_message_text(
        text,
        reply_markup=single_product_manage_keyboard(product_id, product["in_stock"]),
    )


async def admin_toggle_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Статус изменён ✅")

    parts = query.data.split(":")
    product_id = int(parts[2])
    new_value = int(parts[3])

    await db.toggle_product_stock(product_id, new_value)

    product = await db.get_product(product_id)
    status = "✅ В продаже" if product["in_stock"] else "❌ Снят с продажи"
    text = (
        f"📦 {product['name']}\n\n"
        f"Статус: {status}\n"
        f"💰 Цена: {product['price']} ₽\n"
    )
    if product["collection_name"]:
        text += f"🏷 Коллекция: {product['collection_name']}\n"

    await query.edit_message_text(
        text,
        reply_markup=single_product_manage_keyboard(product_id, product["in_stock"]),
    )


async def admin_delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Товар удалён ✅")

    product_id = int(query.data.split(":")[2])
    await db.delete_product(product_id)

    products = await db.get_all_products(include_hidden=True)
    if not products:
        await query.edit_message_text("Товаров больше нет 📦")
        return

    await query.edit_message_text(
        "📦 Управление товарами:\n\n✅ — В продаже\n❌ — Снят с продажи",
        reply_markup=products_manage_keyboard(products),
    )


async def admin_back_manage_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    products = await db.get_all_products(include_hidden=True)
    await query.edit_message_text(
        "📦 Управление товарами:\n\n✅ — В продаже\n❌ — Снят с продажи",
        reply_markup=products_manage_keyboard(products),
    )


# ─── Main ──────────────────────────────────────────────────────────────────────


async def post_init(application: Application) -> None:
    await db.init_db()
    logger.info("База данных инициализирована ✅")


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Commands
    application.add_handler(CommandHandler("start", start))

    # Main menu
    application.add_handler(MessageHandler(filters.Regex("^🏠 В главное меню$"), main_menu_handler))
    application.add_handler(MessageHandler(filters.Regex("^🛍 Каталог$"), catalog))
    application.add_handler(MessageHandler(filters.Regex("^🛒 Корзина$"), cart_view))
    application.add_handler(MessageHandler(filters.Regex("^📦 Мои заказы$"), my_orders))
    application.add_handler(MessageHandler(filters.Regex("^📞 Поддержка$"), support))

    # Admin menu
    application.add_handler(MessageHandler(filters.Regex("^📋 Все заказы$"), admin_orders))
    application.add_handler(MessageHandler(filters.Regex("^📦 Управление товарами$"), admin_manage_products))

    # Catalog
    application.add_handler(CallbackQueryHandler(show_product, pattern=r"^product:\d+$"))
    application.add_handler(CallbackQueryHandler(catalog_back, pattern=r"^catalog:back$"))

    # Cart
    application.add_handler(CallbackQueryHandler(cart_add, pattern=r"^cart:add:\d+$"))
    application.add_handler(CallbackQueryHandler(cart_remove, pattern=r"^cart:remove:\d+$"))
    application.add_handler(CallbackQueryHandler(cart_clear, pattern=r"^cart:clear$"))
    application.add_handler(CallbackQueryHandler(delivery_info_callback, pattern=r"^delivery_info$"))

    # Checkout
    checkout_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(checkout_start, pattern=r"^checkout$")],
        states={
            CHECKOUT_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_address)],
            CHECKOUT_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_comment)],
            CHECKOUT_CONFIRM: [
                CallbackQueryHandler(confirm_order, pattern=r"^confirm_order$"),
                CallbackQueryHandler(cancel_order, pattern=r"^cancel_order$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        name="checkout",
        persistent=False,
    )
    application.add_handler(checkout_conversation)

    # User order actions
    application.add_handler(CallbackQueryHandler(user_order_received, pattern=r"^user:order_received:\d+$"))
    application.add_handler(CallbackQueryHandler(my_orders, pattern=r"^my_orders_back$"))

    # Admin order management
    application.add_handler(CallbackQueryHandler(admin_view_order, pattern=r"^admin:view_order:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_order_delivered, pattern=r"^admin:order_delivered:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_order_cancel, pattern=r"^admin:order_cancel:\d+$"))

    # Admin add track
    track_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_track_start, pattern=r"^admin:order_track:\d+$")],
        states={
            ADD_TRACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_track_save)],
        },
        fallbacks=[CommandHandler("start", admin_track_cancel)],
        name="add_track",
        persistent=False,
    )
    application.add_handler(track_conversation)

    # Admin add product
    add_product_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить товар$"), admin_add_product_start)],
        states={
            ADD_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_name)],
            ADD_PRODUCT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_desc)],
            ADD_PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_price)],
            ADD_PRODUCT_PHOTO: [
                MessageHandler(filters.PHOTO, admin_add_product_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_photo),
            ],
            ADD_PRODUCT_COLLECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_product_collection)],
        },
        fallbacks=[CommandHandler("start", admin_add_product_cancel)],
        name="add_product",
        persistent=False,
    )
    application.add_handler(add_product_conversation)

    # Admin product management
    application.add_handler(CallbackQueryHandler(admin_product_manage, pattern=r"^admin:product_manage:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_toggle_stock, pattern=r"^admin:toggle_stock:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_delete_product, pattern=r"^admin:delete_product:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_back_manage_products, pattern=r"^admin:back_manage_products$"))

    logger.info("Бот запущен 🚀")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
