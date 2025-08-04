import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
from threading import Timer
import time
import json
import threading
import os
from flask import Flask
TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
bot_username = bot.get_me().username

with open("dictionnaire.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    
CREATOR_ID = 7913375184  
SYNONYMES = data["synonymes"]
ANTONYMES = data["antonymes"]
COMMANDES_DM_AUTORISÉES = ["/start", "/gradin", "/bilan" , "/joueurs" , "/reset" ]
VICTOIRES_FILE = "victoires.json"

def load_victoires():
    if not os.path.exists(VICTOIRES_FILE):
        return {}
    with open(VICTOIRES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_victoires(data):
    with open(VICTOIRES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
victoires_globales = load_victoires()
games = {}

class Game:
    def __init__(self, chat_id, mode=None):
        self.chat_id = chat_id
        self.mode = mode
        self.players = []
        self.usernames = {}
        self.current_index = 0
        self.used_words = set()
        self.turn_count = {}
        self.timer = None
        self.active = False
        self.current_word = ""
        self.current_player = None
        self.eliminated = set()
        self.countdown_started = False
        self.countdown_timer = None
        self.countdown_thread = None
        self.countdown_seconds = 30
        self.countdown_cancelled = False

    def get_name(self, user):
        return f"@{user.username}" if user.username else f"<n>{user.first_name}</n>"

    def silent_cancel_countdown(self):
        self.countdown_cancelled = True
        if self.countdown_thread:
            self.countdown_thread.cancel()
            self.countdown_thread = None 

    def cancel_countdown(self):
        self.countdown_cancelled = True
        if self.countdown_thread:
            self.countdown_thread.cancel()
            self.countdown_thread = None
        bot.send_message(self.chat_id, "⏸️ Le compte à rebours est suspendu. Tape /flashgame pour commencer quand tu veux.")

    def start_countdown(self):
        self.countdown_started = True
        self.countdown_seconds = 30
        self.countdown_cancelled = False
        bot.send_message(self.chat_id, "<b>Début automatique dans 30 secondes…</b>", parse_mode="HTML")
        self.countdown_thread = Timer(0, self.countdown_step)
        self.countdown_thread.start()

    def countdown_step(self):
        if self.countdown_cancelled:
            return
        if self.countdown_seconds <= 0:
            self.start_game()
            return
        if self.countdown_seconds in [30, 25, 20, 15, 10, 5]:
            bot.send_message(self.chat_id, f"⏳ Début dans {self.countdown_seconds} secondes…")
        self.countdown_seconds -= 5
        self.countdown_thread = Timer(5, self.countdown_step)
        self.countdown_thread.start()

    def add_player(self, user):
        if user.id in [p.id for p in self.players] or self.active:
            return False
        if len(self.players) >= 4:
            bot.send_message(self.chat_id, "⛔ La partie est pleine (4 joueurs max).")
            return False
        self.players.append(user)
        self.usernames[user.id] = user.username or user.first_name
        self.turn_count[user.id] = 0
        bot.send_message(
            self.chat_id,
            f"✅ {self.get_name(user)} a rejoint la partie ({len(self.players)}/4)",
            parse_mode="HTML"
        )
        if len(self.players) >= 2 and not self.countdown_started:
            self.start_countdown()
        return True

    def start_game(self):
        self.silent_cancel_countdown()  # Remplacé par version silencieuse
        if len(self.players) < 2:
            bot.send_message(self.chat_id, "⛔ Pas assez de joueurs pour commencer.")
            return
        self.active = True
        self.ask_next()

    def ask_next(self):
        if not self.active:
            return
        if self.timer:
            self.timer.cancel()
            self.timer = None
        self.current_player = self.players[self.current_index]
        self.turn_count[self.current_player.id] += 1
        delay = 20 if self.turn_count[self.current_player.id] <= 2 else 10

        word_list = SYNONYMES if self.mode == "synonyme" else ANTONYMES
        word = random.choice(list(word_list.keys()))
        while word in self.used_words:
            word = random.choice(list(word_list.keys()))
        self.current_word = word
        self.used_words.add(word)

        name = self.get_name(self.current_player)
        bot.send_message(
            self.chat_id,
            f"<b>Tour de {name}</b>\n<blockquote>Mot : <b>{word}</b>\nMode : {self.mode}</blockquote>\nTu as {delay} secondes !",
            parse_mode="HTML"
        )

        self.timer = Timer(delay, self.timeout)
        self.timer.start()

    def timeout(self):
        name = self.get_name(self.current_player)
        bot.send_message(self.chat_id, f"❌ <b>{name} a perdu par inactivité !</b>", parse_mode="HTML")
        self.eliminated.add(self.current_player.id)
        self.check_winner_or_continue()

    def validate(self, user, word):
        if not self.active or user.id != self.current_player.id or user.id in self.eliminated:
            return

        word = word.lower().strip()

        if word in self.used_words:
            bot.send_message(self.chat_id, f"⚠️ Ce mot a déjà été utilisé {self.get_name(user)}. Essaie un autre !", parse_mode="HTML")
            return

        valid_list = SYNONYMES.get(self.current_word, []) if self.mode == 'synonyme' else ANTONYMES.get(self.current_word, [])
        if word in valid_list:
            self.used_words.add(word)
            bot.send_message(self.chat_id, f"✅ <b>{self.get_name(user)}</b> a réussi !", parse_mode="HTML")
            if self.timer:
                self.timer.cancel()
                self.timer = None
            self.current_index = (self.current_index + 1) % len(self.players)
            self.skip_eliminated()
            self.ask_next()
            return

        bot.send_message(self.chat_id, f"⚠️ Mauvaise réponse {self.get_name(user)}. Tu peux réessayer !", parse_mode="HTML")

    def skip_eliminated(self):
        while self.players[self.current_index].id in self.eliminated:
            self.current_index = (self.current_index + 1) % len(self.players)


    def check_winner_or_continue(self):
        alive = [p for p in self.players if p.id not in self.eliminated]
        if len(alive) == 1:
            winner = alive[0]
            winner_name = self.get_name(winner)
            bot.send_message(self.chat_id, f"🎉 <b>{winner_name} a gagné la partie !</b>", parse_mode="HTML")
            self.active = False
            if self.timer:
                self.timer.cancel()
                self.timer = None

            # Mise à jour du classement global
            global victoires_globales
            victoires_globales[str(winner.id)] = victoires_globales.get(str(winner.id), 0) + 1
            save_victoires(victoires_globales)

            del games[self.chat_id]
        else:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            self.current_index = (self.current_index + 1) % len(self.players)
            self.skip_eliminated()
            self.ask_next()

### ━━━ Commandes Telegram ━━━

# ➤ Bloque les commandes interdites en DM
@bot.message_handler(func=lambda message: message.chat.type == "private" and message.text.startswith("/") and message.text.split()[0] not in COMMANDES_DM_AUTORISÉES)
def bloquer_commandes_dm(message):
    bot.send_message(message.chat.id, "🚫 Cette commande n'est disponible que dans les groupes.")


@bot.message_handler(commands=['joueurs'])
def nombre_joueurs(message):
    chat_id = message.chat.id

    total = len(victoires_globales)
    texte = f"👥 <b>Nombre de joueurs enregistrés :</b> <code>{total}</code>"

    try:
        bot.send_message(chat_id, texte, parse_mode="HTML")
    except Exception as e:
        print("Erreur envoi nombre de joueurs :", e)
@bot.message_handler(commands=['startgame'])
def start_game(message):
    chat_id = message.chat.id
    user = message.from_user
    if chat_id in games:
        bot.send_message(chat_id, "⚠️ Une partie est déjà en cours ou en attente.")
        return

    # Création de la partie
    games[chat_id] = Game(chat_id)
    games[chat_id].add_player(user)

    # Affichage du menu de sélection de mode
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎯 Synonymes", callback_data="mode_synonyme"),
        InlineKeyboardButton("🚫 Antonymes", callback_data="mode_antonyme")
    )
    bot.send_message(chat_id, "<b>Choisis un mode :</b>", parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['play'])
def join_game(message):
    chat_id = message.chat.id
    user = message.from_user

    if chat_id not in games:
        bot.send_message(chat_id, "⛔ Aucune partie n'est en attente. Lance /startgame pour en créer une.")
        return

    game = games[chat_id]

    if game.active:
        bot.send_message(chat_id, "⛔ La partie a déjà commencé.")
        return

    if game.mode is None:
        bot.send_message(chat_id, "⚠️ Aucun mode choisis.")
        return

    if user.id in [p.id for p in game.players]:
        bot.send_message(chat_id, "ℹ️ Tu es déjà dans la partie.")
        return

    game.add_player(user)
   
@bot.message_handler(commands=['reset'])
def reset_jeu(message):
    if message.from_user.id != CREATOR_ID:
        bot.send_message(message.chat.id, "⛔ Seul le créateur peut utiliser cette commande.")
        return

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Confirmer", callback_data="reset_confirmer"),
        InlineKeyboardButton("❌ Annuler", callback_data="reset_annuler")
    )

    bot.send_message(message.chat.id, "⚠️ Es-tu sûr de vouloir réinitialiser **tout le jeu** ?", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["reset_confirmer", "reset_annuler"])
def confirmation_reset(call):
    if call.from_user.id != CREATOR_ID:
        bot.answer_callback_query(call.id, text="⛔ Réservé au créateur.", show_alert=True)
        return

    if call.data == "reset_annuler":
        bot.edit_message_text("❌ Réinitialisation annulée.", call.message.chat.id, call.message.message_id)
        return

    # ✅ Confirmation → compte à rebours
    def countdown_and_reset():
        for i in [3, 2, 1]:
            bot.edit_message_text(f"🔄 Réinitialisation dans {i}...", call.message.chat.id, call.message.message_id)
            time.sleep(1)

        # Réinitialisation complète
        global victoires_globales, games
        victoires_globales = {}
        games = {}
        save_victoires(victoires_globales)

        bot.edit_message_text("♻️ Le jeu entier a été réinitialisé.", call.message.chat.id, call.message.message_id)

    # Lance dans un thread pour éviter le blocage
    from threading import Thread
    Thread(target=countdown_and_reset).start()

@bot.message_handler(commands=['flashgame'])
def start_game_handler(message):
    chat_id = message.chat.id

    if chat_id not in games:
        bot.send_message(chat_id, "❌ Aucun jeu en attente.")
        return

    game = games[chat_id]

    if game.active:
        bot.send_message(chat_id, "⚠️ Le jeu a déjà commencé.")
        return

    # ✅ Annulation silencieuse et démarrage
    game.silent_cancel_countdown()
    game.start_game()
@bot.message_handler(commands=['gradin'])
def show_gradin(message):
    chat_id = message.chat.id

    if not victoires_globales:
        bot.send_message(chat_id, "ℹ️ Aucun vainqueur enregistré pour le moment.")
        return

    classement = sorted(victoires_globales.items(), key=lambda x: x[1], reverse=True)

    texte = "<b>📊 Classement </b>\n\n<blockquote>"

    medals = ["🥇", "🥈", "🥉"]
    for rang, (user_id, nb_victoires) in enumerate(classement, start=1):
        try:
            user = bot.get_chat(int(user_id))
            nom = f"@{user.username}" if user.username else (user.first_name or f"Utilisateur {user_id}")
        except Exception as e:
            print(f"Erreur get_chat pour user_id={user_id} :", e)
            nom = f"Utilisateur {user_id}"

        medal = medals[rang-1] if rang <= 3 else f"{rang}."
        texte += f"{medal} {nom} — {nb_victoires} victoire{'s' if nb_victoires > 1 else ''}\n"

    texte += "</blockquote>"

    try:
        bot.send_message(chat_id, texte, parse_mode="HTML")
    except Exception as e:
        print("Erreur envoi classement :", e)
@bot.message_handler(commands=['bilan'])
def bilan_personnel(message):
    user_id = str(message.from_user.id)
    chat_id = message.chat.id

    victoires = victoires_globales.get(user_id, 0)
    defaites = 0  # à gérer plus tard

    total = victoires + defaites
    taux = f"{(victoires / total * 100):.1f}%" if total > 0 else "0%"

    classement = sorted(victoires_globales.items(), key=lambda x: x[1], reverse=True)
    position = next((i + 1 for i, (uid, _) in enumerate(classement) if uid == user_id), None)

    def get_statut(pos):
        if pos is None:
            return "🌱 Nouveau venu"
        elif pos == 1:
            return "👑 Légende vivante"
        elif pos <= 3:
            return "🔥 Champion confirmé"
        elif pos <= 10:
            return "⚔️ Combattant aguerri"
        else:
            return "📈 En pleine ascension"

    statut = get_statut(position)

    nom = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    texte = f"<b>📋 Bilan de {nom}</b>\n"
    texte += f"<blockquote><b> 🏆 Victoires : {victoires}</b></blockquote>\n"
    texte += f" <blockquote><b> ☠️ Défaites : {defaites}</b></blockquote>\n"
    texte += f"<blockquote><b> ♟️ Taux de réussite : {taux}</b></blockquote>\n"
    texte += f"<blockquote><b> 🌍 Position : {position if position else 'Non classé'}</b></blockquote>\n"
    texte += f"<blockquote><b> 🏅 Statut : {statut}</b></blockquote>"

    try:
        bot.send_message(chat_id, texte, parse_mode="HTML")
    except Exception as e:
        print("Erreur envoi bilan :", e)
        
@bot.message_handler(commands=['waitgame'])
def wait_game(message):
    chat_id = message.chat.id
    if chat_id in games and not games[chat_id].active:
        game = games[chat_id]
        game.cancel_countdown()

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def choose_mode(call):
    chat_id = call.message.chat.id
    mode = call.data.split("_")[1]
    bot.delete_message(chat_id, call.message.message_id)

    if chat_id in games:
        games[chat_id].mode = mode
    bot.send_message(chat_id, f"🎮 Mode sélectionné : <b>{mode}</b>", parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: True)
def handle_word(message):
    chat_id = message.chat.id
    if chat_id not in games:
        return
    game = games[chat_id]
    if game.active:
        game.validate(message.from_user, message.text)
# ▶️ Flask pour Render


app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Telegram actif via Render ✅"

def run_flask():
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
