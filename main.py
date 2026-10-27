import os
import random
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ЧЕРЕЗ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID_RAW = os.getenv('ADMIN_ID')

if not TOKEN:
    raise ValueError("Ошибка: Переменная окружения BOT_TOKEN не найдена!")
if not ADMIN_ID_RAW:
    raise ValueError("Ошибка: Переменная окружения ADMIN_ID не найдена!")

ADMIN_ID = int(ADMIN_ID_RAW)
DB_NAME = 'database.db'

bot = telebot.TeleBot(TOKEN, parse_mode='Markdown')

# Временные очереди и состояния (в памяти)
users = {}
search_queue = {'Простой чат 💬': [], 'Пошлый чат😈': []}

# Список тем для кнопки "Разбить лёд"
ICEBREAKERS = [
    "Если бы ты мог обладать любой суперспособностью на один день, что бы это было? 🦸‍♂️",
    "Какой самый нелепый или смешной поступок ты совершал в детстве? 🧸",
    "Если бы тебе пришлось есть только одно блюдо всю жизнь, что бы ты выбрал? 🍕",
    "Какая песня у тебя сейчас на повторе? 🎵",
    "Какой фильм или сериал ты готов пересматривать бесконечно? 🎬",
    "Веришь ли ты в инопланетян или мистику? 👽",
    "Какое у тебя самое необычное хобби или интерес? ✨"
]

# === РАБОТА С БАЗОЙ ДАННЫХ SQLITE ===
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                gender TEXT,
                age INTEGER,
                room TEXT DEFAULT 'Простой чат 💬',
                interest TEXT DEFAULT 'Не выбран',
                search_gender TEXT DEFAULT 'Any',
                search_age TEXT DEFAULT 'Any',
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0,
                reports INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def db_get_user(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, gender, age, room, interest, search_gender, search_age, likes, dislikes, reports FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'gender': row[2],
                'age': row[3],
                'room': row[4],
                'interest': row[5],
                'search_gender': row[6],
                'search_age': row[7],
                'likes': row[8],
                'dislikes': row[9],
                'reports': row[10]
            }
        return None

def db_create_user(user_id, username):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username)
            VALUES (?, ?)
        ''', (user_id, username))
        conn.commit()

def db_update_user(user_id, **kwargs):
    if not kwargs:
        return
    set_clause = ', '.join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(f'UPDATE users SET {set_clause} WHERE user_id = ?', values)
        conn.commit()

def get_user_data(user_id, username=None):
    if user_id not in users:
        db_data = db_get_user(user_id)
        if not db_data:
            db_create_user(user_id, username)
            db_data = db_get_user(user_id)
        users[user_id] = {
            **db_data,
            'state': 'idle',
            'partner': None,
            'last_partner': None,
            'contact_shared': False
        }
    elif username and users[user_id].get('username') != username:
        users[user_id]['username'] = username
        db_update_user(user_id, username=username)
    return users[user_id]

# === КЛАВИАТУРЫ ===
def main_menu_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Поиск собеседника 💫"), KeyboardButton("Настройки поиска 🔴"))
    markup.add(KeyboardButton("Выбор комнаты ✨"), KeyboardButton("Мой профиль 💋"))
    markup.add(KeyboardButton("Редактировать профиль 🔥"), KeyboardButton("Изменить интерес 💫"))
    return markup

def chat_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Завершить диалог ✅"), KeyboardButton("Пропустить ➡️"))
    markup.add(KeyboardButton("Разбить лёд 🎲"), KeyboardButton("Обменяться контактами 🔗"))
    return markup

def search_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Пропустить ➡️"), KeyboardButton("Отменить поиск 🔴"))
    return markup

def get_gender_keyboard(action="reg"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Мужской 👨", callback_data=f"{action}_gender_M"),
               InlineKeyboardButton("Женский 👩", callback_data=f"{action}_gender_F"))
    if action == "search":
         markup.add(InlineKeyboardButton("Любой 💝", callback_data=f"{action}_gender_Any"))
    return markup

def get_age_keyboard(action="reg", page=0):
    markup = InlineKeyboardMarkup()
    ages = list(range(6, 56)) 
    per_page = 12
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_ages = ages[start_idx:end_idx]
    
    row = []
    for age in page_ages:
        row.append(InlineKeyboardButton(str(age), callback_data=f"{action}_age_{age}"))
        if len(row) == 4:
            markup.add(*row)
            row = []
    if row:
        markup.add(*row)
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"{action}_page_{page-1}"))
    if end_idx < len(ages):
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"{action}_page_{page+1}"))
    if nav_row:
        markup.add(*nav_row)
    return markup

def get_search_age_keyboard():
    markup = InlineKeyboardMarkup()
    ranges = [
        ("6-12 лет", "6-12"), ("13-17 лет", "13-17"), ("18-25 лет", "18-25"),
        ("19-28 лет 🔥", "19-28"), ("29-35 лет", "29-35"), ("36-45 лет", "36-45"),
        ("46-55 лет", "46-55"), ("Любой возраст 💝", "Any")
    ]
    row = []
    for text, val in ranges:
        row.append(InlineKeyboardButton(text, callback_data=f"search_age_{val}"))
        if len(row) == 2:
            markup.add(*row)
            row = []
    if row:
        markup.add(*row)
    return markup

def get_room_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Простой чат 💬", callback_data="room_Простой чат 💬"))
    markup.add(InlineKeyboardButton("Пошлый чат😈", callback_data="room_Пошлый чат😈"))
    return markup

def get_interest_keyboard(room):
    markup = InlineKeyboardMarkup()
    if room == 'Пошлый чат😈':
        interests = ["Вирт", "Пошлое общение", "Вирт 18+"]
    else:
        interests = ["Аниме", "Программирование", "Музыка", "Игры", 
                     "Кино", "Спорт", "Книги", "Творчество", 
                     "Просто общение", "Другое"]
        
    row = []
    for inter in interests:
        row.append(InlineKeyboardButton(inter, callback_data=f"set_interest_{inter}"))
        if len(row) == 2:
            markup.add(*row)
            row = []
    if row:
        markup.add(*row)
    return markup

def get_rating_keyboard(partner_id):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("👍 Интересный", callback_data=f"rate_like_{partner_id}"),
        InlineKeyboardButton("👎 Скучный", callback_data=f"rate_dislike_{partner_id}")
    )
    markup.add(InlineKeyboardButton("🚨 Пожаловаться", callback_data=f"report_{partner_id}"))
    return markup

# === ЛОГИКА И СИСТЕМА КАРМЫ ===
def is_user_banned_from_nsfw(user_id):
    u = users[user_id]
    if u.get('reports', 0) >= 3:
        return True
        
    likes = u.get('likes', 0)
    dislikes = u.get('dislikes', 0)
    total = likes + dislikes
    
    if total >= 5 and (dislikes / total) >= 0.7:
        return True
    return False

def age_matches(search_setting, actual_age):
    if search_setting == 'Any': 
        return True
    try:
        min_age, max_age = map(int, search_setting.split('-'))
        return min_age <= actual_age <= max_age
    except Exception:
        return False

def find_partner(user_id):
    user = users[user_id]
    room = user.get('room', 'Простой чат 💬')
    
    for partner_id in search_queue[room]:
        if partner_id == user_id: 
            continue
        
        if partner_id == user.get('last_partner') or user_id == users[partner_id].get('last_partner'):
            continue
            
        p = users[partner_id]
        gender_match_1 = (user['search_gender'] == 'Any' or user['search_gender'] == p['gender'])
        gender_match_2 = (p['search_gender'] == 'Any' or p['search_gender'] == user['gender'])
        
        age_match_1 = age_matches(user['search_age'], p['age'])
        age_match_2 = age_matches(p['search_age'], user['age'])
        
        if gender_match_1 and gender_match_2 and age_match_1 and age_match_2:
            return partner_id
    return None

def get_admin_secret_info(partner_id, p_data):
    info = "\n\n🕵️‍♂️ *СЕКРЕТНАЯ ИНФО (Ты Админ):*\n"
    info += f"ID: `{partner_id}` | @{p_data.get('username', 'Скрыт')}\n"
    info += f"Пол: {p_data['gender']} | Возраст: {p_data['age']} лет\n"
    info += f"Ищет: {p_data['search_gender']}, {p_data['search_age']}\n"
    info += f"Рейтинг: 👍 {p_data.get('likes', 0)} | 👎 {p_data.get('dislikes', 0)} | 🚨 Жалоб: {p_data.get('reports', 0)}"
    return info

def start_chat(user1, user2, room):
    if user1 in search_queue[room]: search_queue[room].remove(user1)
    if user2 in search_queue[room]: search_queue[room].remove(user2)
    
    users[user1].update({'state': 'chatting', 'partner': user2, 'contact_shared': False})
    users[user2].update({'state': 'chatting', 'partner': user1, 'contact_shared': False})
    
    msg1 = f"Собеседник найден! 🫦\nУ данного пользователя интерес: [{users[user2]['interest']}]\nПриятного общения!"
    msg2 = f"Собеседник найден! 🫦\nУ данного пользователя интерес: [{users[user1]['interest']}]\nПриятного общения!"
    
    if user1 == ADMIN_ID: msg1 += get_admin_secret_info(user2, users[user2])
    if user2 == ADMIN_ID: msg2 += get_admin_secret_info(user1, users[user1])
    
    bot.send_message(user1, msg1, reply_markup=chat_keyboard())
    bot.send_message(user2, msg2, reply_markup=chat_keyboard())

def execute_disconnect(uid, pid, show_partner_alert=True):
    if uid in users:
        users[uid].update({'state': 'idle', 'partner': None, 'last_partner': pid, 'contact_shared': False})
        bot.send_message(uid, "Оцени собеседника:", reply_markup=get_rating_keyboard(pid))
        
    if pid in users:
        users[pid].update({'state': 'idle', 'partner': None, 'last_partner': uid, 'contact_shared': False})
        if show_partner_alert:
            bot.send_message(pid, "Собеседник покинул чат. 🔴")
        bot.send_message(pid, "Оцени собеседника:", reply_markup=get_rating_keyboard(uid))

def trigger_search(user_id):
    user = users[user_id]
    bot.send_message(user_id, "Поиск начался! Ищу собеседника по вашим настройкам…", reply_markup=search_keyboard())
    user['state'] = 'searching'
    if user_id not in search_queue[user['room']]:
        search_queue[user['room']].append(user_id)
        
    partner = find_partner(user_id)
    if partner:
        start_chat(user_id, partner, user['room'])

# === КОМАНДЫ ===
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    username = message.from_user.username
    user = get_user_data(user_id, username)
    
    welcome_text = (
        "Привет! Я бот Чат Рулетка. Мой функционал полностью бесплатный!❤️\n\n"
        "• Поиск по полу и возрасту\n"
        "• Выбор комнаты \n"
        "• Выбор интересов и так далее!\n\n"
        "Весь мой функционал полностью бесплатный, и не требует никаких подписок🔥"
    )
    bot.send_message(user_id, welcome_text)

    if not user.get('age') or not user.get('gender'):
        bot.send_message(user_id, "Выбери свой пол. Выбери свой честный возраст (Выбор от 6 до 55 лет).", reply_markup=get_gender_keyboard("reg"))
    else:
        bot.send_message(user_id, "Вы уже зарегистрированы! Добро пожаловать обратно.", reply_markup=main_menu_keyboard())

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        return
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        total_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT user_id, username, gender, age, room, interest, likes, dislikes, reports FROM users WHERE age IS NOT NULL ORDER BY user_id DESC LIMIT 30')
        all_db_users = cursor.fetchall()
        
    text = "🔥 *СУПЕР АДМИНКА (SQLite)* 🔥\n\n"
    text += f"Всего зарегистрировано пользователей: {total_count}\n"
    text += f"В очереди поиска (Простой): {len(search_queue['Простой чат 💬'])}\n"
    text += f"В очереди поиска (Пошлый): {len(search_queue['Пошлый чат😈'])}\n\n"
    text += "📋 *Последние пользователи:*\n"
    
    for row in all_db_users:
        uid, uname, gen, age, room, inter, lk, dlk, rep = row
        uname_display = f"@{uname}" if uname else "-"
        text += f"ID: `{uid}` | {uname_display} | {gen}, {age} лет | Интерес: {inter} | 👍{lk} 👎{dlk} 🚨{rep} | Зал: {room}\n"
            
    bot.send_message(ADMIN_ID, text)

# === ОБРАБОТКА ИНЛАЙН КНОПОК ===
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try: 
        bot.answer_callback_query(call.id)
    except Exception: 
        pass

    user_id = call.message.chat.id
    user = get_user_data(user_id, call.from_user.username)
    data = call.data
    
    if data.startswith("reg_gender_"):
        gender = data.split("_")[2]
        user['gender'] = gender
        db_update_user(user_id, gender=gender)
        bot.edit_message_text("Теперь выбери свой честный возраст:", user_id, call.message.message_id, reply_markup=get_age_keyboard("reg", page=0))
        
    elif data.startswith("reg_page_"):
        page = int(data.split("_")[2])
        bot.edit_message_text("Теперь выбери свой честный возраст:", user_id, call.message.message_id, reply_markup=get_age_keyboard("reg", page=page))

    elif data.startswith("reg_age_"):
        age = int(data.split("_")[2])
        user['age'] = age
        db_update_user(user_id, age=age)
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, "Регистрация завершена! ✅ Выбери комнату:", reply_markup=get_room_keyboard())

    elif data.startswith("room_"):
        selected_room = data.split("_")[1]
        
        if selected_room == 'Пошлый чат😈':
            if user['age'] < 18:
                markup = InlineKeyboardMarkup().add(InlineKeyboardButton("Поменять возраст 📝", callback_data="change_age_flow"))
                bot.send_message(user_id, "Пошлый чат доступен только с 18 лет! 🔴\nЕсли вы случайно указали неверный возраст, измените его:", reply_markup=markup)
                return
            if is_user_banned_from_nsfw(user_id):
                bot.send_message(user_id, "Вам заблокирован доступ в эту комнату из-за слишком низкого рейтинга кармы или жалоб. 🔴")
                return
            
        user['room'] = selected_room
        db_update_user(user_id, room=selected_room)
        bot.send_message(user_id, f"Выбрана комната: {selected_room}\nТеперь выбери свой интерес: ✨", reply_markup=get_interest_keyboard(selected_room))

    elif data.startswith("set_interest_"):
        chosen_interest = data.split("_")[2]
        user['interest'] = chosen_interest
        db_update_user(user_id, interest=chosen_interest)
        bot.delete_message(user_id, call.message.message_id)
        bot.send_message(user_id, f"Твой интерес сохранен: [{chosen_interest}]! ✅\nТеперь можешь искать собеседника!", reply_markup=main_menu_keyboard())

    elif data.startswith("rate_like_"):
        pid = int(data.split("_")[2])
        p_user = get_user_data(pid)
        p_user['likes'] = p_user.get('likes', 0) + 1
        db_update_user(pid, likes=p_user['likes'])
        bot.edit_message_text("Спасибо за оценку! ✅", user_id, call.message.message_id, reply_markup=None)

    elif data.startswith("rate_dislike_"):
        pid = int(data.split("_")[2])
        p_user = get_user_data(pid)
        p_user['dislikes'] = p_user.get('dislikes', 0) + 1
        db_update_user(pid, dislikes=p_user['dislikes'])
        bot.edit_message_text("Спасибо за оценку! ✅", user_id, call.message.message_id, reply_markup=None)
        
    elif data.startswith("report_"):
        pid = int(data.split("_")[1])
        p_user = get_user_data(pid)
        p_user['reports'] = p_user.get('reports', 0) + 1
        db_update_user(pid, reports=p_user['reports'])
        if pid != ADMIN_ID:
            bot.send_message(ADMIN_ID, f"🚨 *ЖАЛОБА!*\nПоступила жалоба на пользователя ID: `{pid}` (@{p_user.get('username','-')}). Всего жалоб: {p_user['reports']}")
        bot.edit_message_text("Жалоба отправлена модераторам. Спасибо! ✅", user_id, call.message.message_id, reply_markup=None)

    elif data == "change_age_flow":
        bot.send_message(user_id, "Давай исправим профиль. Выбери свой пол:", reply_markup=get_gender_keyboard("reg"))

    elif data.startswith("search_gender_"):
        s_gender = data.split("_")[2]
        user['search_gender'] = s_gender
        db_update_user(user_id, search_gender=s_gender)
        bot.edit_message_text("Какого возраста собеседника ты ищешь? 💫", user_id, call.message.message_id, reply_markup=get_search_age_keyboard())
        
    elif data.startswith("search_age_"):
        s_age = data.split("_")[2]
        user['search_age'] = s_age
        db_update_user(user_id, search_age=s_age)
        bot.delete_message(user_id, call.message.message_id)
        
        g_text = "Любого" if user['search_gender'] == 'Any' else ("Мужского" if user['search_gender'] == 'M' else "Женского")
        a_text = "любого возраста" if user['search_age'] == 'Any' else f"в диапазоне {user['search_age']} лет"
        
        bot.send_message(user_id, f"Настройки поиска обновлены! ✅\nИщем: пользователя {g_text} пола, {a_text}.", reply_markup=main_menu_keyboard())

# === ОБРАБОТКА ТЕКСТА И КНОПОК ===
@bot.message_handler(content_types=['text'])
def text_handler(message):
    user_id = message.chat.id
    user = get_user_data(user_id, message.from_user.username)
    text = message.text
    
    if user['state'] == 'chatting':
        partner_id = user['partner']
        
        if text == "Завершить диалог ✅":
            execute_disconnect(user_id, partner_id, show_partner_alert=True)
            bot.send_message(user_id, "Возврат в главное меню.", reply_markup=main_menu_keyboard())
            if partner_id in users: 
                bot.send_message(partner_id, "Возврат в главное меню.", reply_markup=main_menu_keyboard())
            return
            
        elif text == "Пропустить ➡️":
            execute_disconnect(user_id, partner_id, show_partner_alert=True)
            if partner_id in users: 
                bot.send_message(partner_id, "Возврат в главное меню.", reply_markup=main_menu_keyboard())
            trigger_search(user_id)
            return
            
        elif text == "Разбить лёд 🎲":
            topic = random.choice(ICEBREAKERS)
            bot.send_message(user_id, f"🎲 *Тема для обсуждения:*\n{topic}")
            bot.send_message(partner_id, f"🎲 *Тема для обсуждения:*\n{topic}")
            return
            
        elif text == "Обменяться контактами 🔗":
            user['contact_shared'] = True
            p_data = get_user_data(partner_id)
            if p_data.get('contact_shared'):
                u1_link = f"@{user.get('username')}" if user.get('username') else "У пользователя скрыт никнейм"
                u2_link = f"@{p_data.get('username')}" if p_data.get('username') else "У пользователя скрыт никнейм"
                bot.send_message(user_id, f"✨ Взаимное согласие! Контакт собеседника: {u2_link}")
                bot.send_message(partner_id, f"✨ Взаимное согласие! Контакт собеседника: {u1_link}")
            else:
                bot.send_message(user_id, "Ожидаем согласия собеседника... ⏳")
                bot.send_message(partner_id, "🔗 Собеседник хочет обменяться контактами! Нажми 'Обменяться контактами 🔗', чтобы согласиться.")
            return
            
        else:
            try: 
                bot.send_message(partner_id, text, parse_mode=None)
            except Exception:
                bot.send_message(user_id, "Собеседник отключился от бота.", reply_markup=main_menu_keyboard())
                user['state'] = 'idle'
        return

    if user['state'] == 'searching':
        if text == "Пропустить ➡️":
            bot.send_message(user_id, "Перезапускаю поиск...")
            if user_id in search_queue[user['room']]: 
                search_queue[user['room']].remove(user_id)
            trigger_search(user_id)
            return
        elif text == "Отменить поиск 🔴":
            if user_id in search_queue[user['room']]: 
                search_queue[user['room']].remove(user_id)
            user['state'] = 'idle'
            bot.send_message(user_id, "Поиск отменен. ✅", reply_markup=main_menu_keyboard())
            return

    if text == "Поиск собеседника 💫":
        if not user.get('age') or not user.get('gender'):
            bot.send_message(user_id, "Сначала пройдите регистрацию!", reply_markup=get_gender_keyboard("reg"))
            return
        trigger_search(user_id)
            
    elif text == "Настройки поиска 🔴":
        bot.send_message(user_id, "Собеседника какого пола ты ищешь?", reply_markup=get_gender_keyboard("search"))
        
    elif text == "Выбор комнаты ✨":
        bot.send_message(user_id, "Выбери комнату:", reply_markup=get_room_keyboard())
        
    elif text == "Мой профиль 💋":
        gender = "Мужской" if user.get('gender') == 'M' else ("Женский" if user.get('gender') == 'F' else "Не указан")
        search_g = "Любой" if user.get('search_gender') == 'Any' else ("Мужской" if user.get('search_gender') == 'M' else "Женский")
        likes_rating = f"👍 {user.get('likes', 0)} | 👎 {user.get('dislikes', 0)}"
        
        bot.send_message(user_id, f"Твой профиль 💋:\nПол: {gender}\nВозраст: {user.get('age', 'Не указан')} лет\nКомната: {user.get('room')}\nИнтерес: {user.get('interest')}\nРейтинг: {likes_rating}\n\nНастройки поиска:\nПол: {search_g} | Возраст: {user.get('search_age')}", reply_markup=main_menu_keyboard())

    elif text == "Редактировать профиль 🔥":
        bot.send_message(user_id, "Запускаю перерегистрацию данных. Выбери свой пол:", reply_markup=get_gender_keyboard("reg"))
        
    elif text == "Изменить интерес 💫":
        bot.send_message(user_id, f"Выбери новый интерес для комнаты [{user.get('room')}]: ✨", reply_markup=get_interest_keyboard(user.get('room')))

# === ОГРАНИЧЕНИЕ МЕДИАФАЙЛОВ ===
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    bot.send_message(message.chat.id, "Только медиафайлы! Документы (в т.ч. PDF) передавать запрещено 🔴")

@bot.message_handler(content_types=['photo', 'video', 'animation', 'voice', 'video_note', 'audio'])
def handle_media(message):
    user_id = message.chat.id
    user = get_user_data(user_id)
    if user and user.get('state') == 'chatting' and user.get('partner'):
        try: 
            bot.copy_message(user['partner'], user_id, message.message_id)
        except Exception: 
            bot.send_message(user_id, "Не удалось переслать медиафайл.")

if __name__ == '__main__':
    init_db()
    print("База данных SQLite подключена...")
    print("Бот запущен...")
    bot.infinity_polling(skip_pending=True)
