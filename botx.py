import sqlite3
import asyncio
import datetime
import os
import random
import discord
from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents, case_insensitive=True)

# Sadece izin verilen kanal ID'si
ALLOWED_CHANNEL_ID = 1535753835308392509

# --- KALICI DİSK VERİTABANI SİSTEMİ (Paralar asla silinmez!) ---
db_path = "/var/data/economy.db" if os.path.exists("/var/data") else "economy.db"
db = sqlite3.connect(db_path)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS economy (
    user_id TEXT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    bank INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    game_count INTEGER DEFAULT 0
)
""")
db.commit()

# Eski tablolarda game_count sütunu yoksa hata vermemesi için ekleyelim:
try:
    cursor.execute("ALTER TABLE economy ADD COLUMN game_count INTEGER DEFAULT 0")
    db.commit()
except:
    pass

def get_balance(user_id):
    user_id = str(user_id)
    cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result is None:
        cursor.execute("INSERT OR REPLACE INTO economy (user_id, balance, bank, streak, game_count) VALUES (?, 0, 0, 0, 0)", (user_id,))
        db.commit()
        return 0
    return result[0]

def get_bank(user_id):
    user_id = str(user_id)
    cursor.execute("SELECT bank FROM economy WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result is None:
        cursor.execute("INSERT OR REPLACE INTO economy (user_id, balance, bank, streak, game_count) VALUES (?, 0, 0, 0, 0)", (user_id,))
        db.commit()
        return 0
    return result[0]

def update_balance(user_id, amount):
    user_id = str(user_id)
    cursor.execute("UPDATE economy SET balance = ? WHERE user_id = ?", (amount, user_id))
    db.commit()

def update_bank(user_id, amount):
    user_id = str(user_id)
    cursor.execute("UPDATE economy SET bank = ? WHERE user_id = ?", (amount, user_id))
    db.commit()

def check_and_update_pity(user_id):
    """Her 20 oyunda 1 kez kesin kazanma (20'de 1) mantığı"""
    user_id = str(user_id)
    cursor.execute("SELECT game_count FROM economy WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    count = (res[0] if res else 0) + 1
    
    if count >= 20:
        cursor.execute("UPDATE economy SET game_count = 0 WHERE user_id = ?", (user_id,))
        db.commit()
        return True # 20. oyun, kesin kazandır!
    else:
        cursor.execute("UPDATE economy SET game_count = ? WHERE user_id = ?", (count, user_id))
        db.commit()
        return False

def get_bet_amount(user_id, amount_str):
    balance = get_balance(user_id)
    if amount_str.lower() == "all":
        return balance
    try:
        amount = int(amount_str)
        return amount
    except:
        return None

# --- OTOMATİK KANAL KONTROLÜ (Global Check) ---
@bot.check
async def globally_block_channels(ctx):
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        return False
    return True

# --- OTOMATİK FAİZ DÖNGÜSÜ (Her 1 saate bir %10 faiz) ---
@tasks.loop(hours=1)
async def bank_interest():
    cursor.execute("SELECT user_id, bank FROM economy WHERE bank > 0")
    users = cursor.fetchall()
    for user_id, current_bank in users:
        added_interest = int(current_bank * 0.10)
        new_bank = current_bank + added_interest
        cursor.execute("UPDATE economy SET bank = ? WHERE user_id = ?", (new_bank, user_id))
    db.commit()

@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user.name}")
    if not bank_interest.is_running():
        bank_interest.start()

# --- GÜNLÜK ÖDÜL ---
@bot.command(name="daily")
async def daily(ctx):
    user_id = str(ctx.author.id)
    cursor.execute("SELECT streak FROM economy WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    streak = res[0] if res else 0
    if streak == 0:
        streak = 1

    reward = streak * 5000
    current_bal = get_balance(user_id)
    update_balance(user_id, current_bal + reward)
    
    cursor.execute("UPDATE economy SET streak = ? WHERE user_id = ?", (streak + 1, user_id))
    db.commit()
    
    await ctx.send(f"🎁 **{ctx.author.name}**, günlük ödülün: **{reward:,} 🪙**. Bir sonraki ödülün **{(streak + 1) * 5000:,} 🪙** olacak!")

# ==========================================
# --- GERÇEK RULET SİSTEMİ (Animasyonlu) ---
# ==========================================
@bot.command(name="rulet")
@commands.cooldown(1, 10, commands.BucketType.user)
async def rulet(ctx, choice: str, amount_str: str):
    user_id = str(ctx.author.id)
    choice = choice.lower()
    
    amount = get_bet_amount(user_id, amount_str)
    current_bal = get_balance(user_id)
    if amount is None or amount <= 0 or current_bal < amount:
        return await ctx.send("Geçersiz miktar veya yetersiz bakiye kanka!")

    red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
    
    is_valid_choice = False
    if choice in ["kırmızı", "siyah", "yeşil", "tek", "cift"]:
        is_valid_choice = True
    elif choice.isdigit():
        num_val = int(choice)
        if 0 <= num_val <= 36:
            is_valid_choice = True
            
    if not is_valid_choice:
        return await ctx.send("Yanlış seçim kanka! Şunlardan birini yazmalısın:\n• `rulet kırmızı [miktar]`\n• `rulet siyah [miktar]`\n• `rulet tek/cift [miktar]`\n• `rulet [0-36 arası sayı] [miktar]`")

    msg = await ctx.send("🎡 Çark döndürülüyor... Top hızla dönüyor 🔄")
    
    anim_steps = [
        "🎡 Top dönüyor: 🔴 **14 (Kırmızı)**",
        "🎡 Top dönüyor: ⬛ **22 (Siyah)**",
        "🎡 Top dönüyor: 🟢 **0 (Yeşil)**",
        "🎡 Top dönüyor: 🔴 **7 (Kırmızı)**",
        "🎡 Top dönüyor: ⬛ **31 (Siyah)**",
        "🎡 Yavaşlıyor... 🔄"
    ]
    
    for step in anim_steps:
        await asyncio.sleep(0.5)
        await msg.edit(content=step)
    
    await asyncio.sleep(0.6)

    forced_win = check_and_update_pity(user_id)
    
    if forced_win:
        if choice == "kırmızı":
            landed_number = random.choice(red_numbers)
        elif choice == "siyah":
            landed_number = random.choice(black_numbers)
        elif choice == "yeşil":
            landed_number = 0
        elif choice == "tek":
            landed_number = random.choice([n for n in range(1, 37) if n % 2 != 0])
        elif choice == "cift":
            landed_number = random.choice([n for n in range(1, 37) if n % 2 == 0])
        else:
            landed_number = int(choice)
    else:
        landed_number = random.randint(0, 36)

    if landed_number == 0:
        color_name = "🟢 YEŞİL (0)"
    elif landed_number in red_numbers:
        color_name = f"🔴 KIRMIZI ({landed_number})"
    else:
        color_name = f"⬛ SİYAH ({landed_number})"

    won = 0
    won_flag = False

    if choice.isdigit() and int(choice) == landed_number:
        won = amount * 35
        won_flag = True
    elif choice == "kırmızı" and landed_number in red_numbers:
        won = amount * 2
        won_flag = True
    elif choice == "siyah" and landed_number in black_numbers:
        won = amount * 2
        won_flag = True
    elif choice == "yeşil" and landed_number == 0:
        won = amount * 14
        won_flag = True
    elif choice == "tek" and landed_number != 0 and landed_number % 2 != 0:
        won = amount * 2
        won_flag = True
    elif choice == "cift" and landed_number != 0 and landed_number % 2 == 0:
        won = amount * 2
        won_flag = True

    if won_flag:
        update_balance(user_id, current_bal + won)
        await msg.edit(content=f"🎯 Çark durdu! Top **{color_name}** üzerinde durdu! Tebrikler kazandın! +**{won:,} 🪙**")
    else:
        update_balance(user_id, current_bal - amount)
        await msg.edit(content=f"😢 Çark durdu! Top **{color_name}** üzerinde durdu. Kaybettin kanka! -**{amount:,} 🪙**")

# --- KASA AÇMA SİSTEMİ ---
@bot.command(name="kasa", aliases=["lootbox"])
@commands.cooldown(1, 10, commands.BucketType.user)
async def open_box(ctx, box_type: str = None):
    user_id = str(ctx.author.id)
    
    if not box_type or box_type.lower() not in ["normal", "lüks", "luks", "mega"]:
        return await ctx.send("Hangi kasayı açmak istiyorsun kanka? Seçenekler:\n• `kasa normal` (10.000 🪙 - En az 1.000)\n• `kasa lüks` (50.000 🪙 - En az 10.000)\n• `kasa mega` (100.000 🪙 - En az 50.000)")
        
    box_type = box_type.lower()
    
    if box_type == "normal":
        price = 10000
    elif box_type in ["lüks", "luks"]:
        box_type = "lüks"
        price = 50000
    else:
        price = 100000
        
    current_bal = get_balance(user_id)
    if current_bal < price:
        return await ctx.send(f"Yetersiz bakiye kanka! Bu kasayı açmak için **{price:,} 🪙** gerekiyor.")
        
    update_balance(user_id, current_bal - price)
    
    msg = await ctx.send("📦 Kasa açılıyor, içerisi taranıyor...")
    await asyncio.sleep(1.5)
    
    if box_type == "normal":
        reward = random.choices(
            [random.randint(1000, 5000), random.randint(5001, 15000), random.randint(15001, 25000)],
            weights=[50, 35, 15], k=1
        )[0]
    elif box_type == "lüks":
        reward = random.choices(
            [random.randint(10000, 30000), random.randint(30001, 55000), random.randint(55001, 80000)],
            weights=[50, 35, 15], k=1
        )[0]
    else:
        reward = random.choices(
            [random.randint(50000, 80000), random.randint(80001, 120000), random.randint(120001, 180000)],
            weights=[50, 35, 15], k=1
        )[0]
        
    update_balance(user_id, get_balance(user_id) + reward)
    await msg.edit(content=f"🎉 Açtığın **{box_type.upper()} Kasa**'dan **+{reward:,} 🪙** çıktı!")

# --- MESAJ SİLME KOMUTU (!sil <sayı>) ---
@bot.command(name="sil")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("Silinecek miktar 0'dan büyük olmalı kanka!")
    
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"🧹 Başarıyla **{len(deleted) - 1}** mesaj silindi kanka!")
    await asyncio.sleep(3)
    await msg.delete()

@clear_messages.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Eyvah kanka! Bu komutu kullanmak için **Mesajları Yönet** yetkin olmalı!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Kaç adet mesaj sileceğimi yazmadın kanka! Örnek: `sil 10`")

# --- BANKA: PARA YATIRMA (DEPOSIT) ---
@bot.command(name="deposit")
async def deposit(ctx, amount_str: str):
    user_id = str(ctx.author.id)
    bal = get_balance(user_id)
    amount = bal if amount_str.lower() == "all" else int(amount_str) if amount_str.isdigit() else 0
    
    if amount <= 0 or bal < amount:
        return await ctx.send("Geçersiz miktar veya yetersiz cüzdan!")
        
    update_balance(user_id, bal - amount)
    update_bank(user_id, get_bank(user_id) + amount)
    await ctx.send(f"🏦 Cüzdanından **{amount:,} 🪙** bankaya yatırıldı.")

# --- BANKA: PARA ÇEKME (WITHDRAW) ---
@bot.command(name="withdraw")
async def withdraw(ctx, amount_str: str):
    user_id = str(ctx.author.id)
    bank = get_bank(user_id)
    amount = bank if amount_str.lower() == "all" else int(amount_str) if amount_str.isdigit() else 0
    
    if amount <= 0 or bank < amount:
        return await ctx.send("Geçersiz miktar veya yetersiz banka bakiyesi!")
        
    update_bank(user_id, bank - amount)
    update_balance(user_id, get_balance(user_id) + amount)
    await ctx.send(f"💸 Bankadan **{amount:,} 🪙** çekildi.")

# --- SERVET SIRALAMASI (LB) ---
@bot.command(name="lb")
async def leaderboard(ctx):
    cursor.execute("SELECT user_id, balance, bank FROM economy")
    rows = cursor.fetchall()
    if not rows:
        return await ctx.send("Henüz sıralamada kimse yok!")
        
    net_worths = [(row[0], row[1] + row[2]) for row in rows]
    sorted_users = sorted(net_worths, key=lambda item: item[1], reverse=True)[:10]
    
    embed = discord.Embed(title="🏆 HelperX - Servet Sıralaması", color=discord.Color.gold())
    desc = "".join([f"**{idx}.** <@!{uid}> — **{total:,}** 🪙\n" for idx, (uid, total) in enumerate(sorted_users, 1)])
    embed.description = desc
    await ctx.send(embed=embed)

# --- MAĞAZA (SHOP) & BUY ---
@bot.command(name="shop")
async def shop(ctx):
    embed = discord.Embed(title="🛒 HelperX Mağaza", description="Paranı harcayarak özel rol alabilirsin!", color=discord.Color.blue())
    embed.add_field(name="VIP Rolü", value="Fiyat: **100000000 🪙**\nKomut: `buy vip`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="buy")
async def buy(ctx, item: str = None):
    if not item or item.lower() != "vip":
        return await ctx.send("Mağazada sadece `buy vip` ürünü bulunuyor!")
        
    user_id = str(ctx.author.id)
    bal = get_balance(user_id)
    price = 100000000
    
    if bal < price:
        return await ctx.send(f"Yetersiz bakiye! VIP için **{price:,} 🪙** gerekiyor.")
        
    update_balance(user_id, bal - price)
    
    role = discord.utils.get(ctx.guild.roles, name="VIP")
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"🎉 Tebrikler! **100000000 🪙** ödeyerek VIP rolünü aldın.")
    else:
        await ctx.send("Paran çekildi fakat sunucuda 'VIP' rolü bulunamadı!")

# --- PROFİL ---
@bot.command(name="profile")
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_id = str(target.id)
    bal = get_balance(user_id)
    bank = get_bank(user_id)
    total = bal + bank
    
    cursor.execute("SELECT streak FROM economy WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    streak = res[0] if res else 0
    
    embed = discord.Embed(title=f"👤 {target.name} - Profil Kartı", color=discord.Color.from_rgb(0, 162, 232))
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🪙 Cüzdan", value=f"**{bal:,}**", inline=True)
    embed.add_field(name="🏦 Banka", value=f"**{bank:,}**", inline=True)
    embed.add_field(name="💰 Toplam Servet", value=f"**{total:,}**", inline=True)
    embed.add_field(name="🔥 Günlük Seri", value=f"**{streak}** gün", inline=True)
    await ctx.send(embed=embed)

# --- YÖNETİCİ VE TRANSFER KOMUTLARI ---
@bot.command(name="add")
@commands.has_permissions(administrator=True)
async def add_money(ctx, amount: int):
    user_id = str(ctx.author.id)
    update_balance(user_id, get_balance(user_id) + amount)
    await ctx.send(f"👑 Cüzdanına **{amount:,}** eklendi!")

@bot.command(name="hparasil")
@commands.has_permissions(administrator=True)
async def hparasil(ctx, member: discord.Member, amount: int):
    user_id = str(member.id)
    current_bal = get_balance(user_id)
    
    if amount <= 0:
        return await ctx.send("Silinecek miktar 0'dan büyük olmalı kanka!")
        
    new_bal = max(0, current_bal - amount)
    update_balance(user_id, new_bal)
    
    await ctx.send(f"⚠️ **{member.name}** adlı kişinin cüzdanından **{amount:,} 🪙** silindi! Güncel cüzdan: **{new_bal:,} 🪙**")

@hparasil.error
async def hparasil_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Eyvah kanka! Bu komutu kullanmak için **Yönetici** yetkin olmalı!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Eksik tuşladın kanka! Örnek kullanım: `hparasil @Kullanici 5000`")

@bot.command(name="hpay")
async def hpay(ctx, member: discord.Member, amount: int):
    sender_id = str(ctx.author.id)
    receiver_id = str(member.id)
    
    if sender_id == receiver_id:
        await ctx.send("Kendine nar gönderemezsin kanka!")
        return

    if amount <= 0:
        await ctx.send("Gönderilecek miktar 0'dan büyük olmalı!")
        return

    if amount > 10000000:
        await ctx.send("Tek seferde en fazla **10000000 🪙** gönderebilirsin!")
        return
        
    sender_wallet = get_balance(sender_id)
    if sender_wallet < amount:
        await ctx.send("Cüzdanında transfer için yeterli para yok!")
        return

    update_balance(sender_id, sender_wallet - amount)
    update_balance(receiver_id, get_balance(receiver_id) + amount)
    
    await ctx.send(f"💸 **{member.name}** kişisine **{amount:,} 🪙** gönderildi!")

# ==========================================
# --- COINFLIP (HF) - 20'de 1 Kesin Kazanma ---
# ==========================================
@bot.command(name="hf")
@commands.cooldown(1, 10, commands.BucketType.user)
async def coinflip(ctx, amount_str: str):
    user_id = str(ctx.author.id)
    amount = get_bet_amount(user_id, amount_str)
    if not amount or amount <= 0:
        return await ctx.send("Geçersiz miktar kanka! Örnek: `hf 1000`")
    current_bal = get_balance(user_id)
    if current_bal < amount:
        return await ctx.send("Yetersiz bakiye kanka!")

    forced_win = check_and_update_pity(user_id)
    win_chance = forced_win or random.choices([True, False], weights=[5, 95], k=1)[0]

    if win_chance:
        update_balance(user_id, current_bal + amount)
        await ctx.send(f"🪙 **{ctx.author.name}** kazandı! +**{amount * 2:,} 🪙**")
    else:
        update_balance(user_id, current_bal - amount)
        await ctx.send(f"🪙 **{ctx.author.name}** kaybetti! -**{amount:,} 🪙** :c")

# ==========================================
# --- SLOTS (HS / WS) - 20'de 1 Kesin Kazanma ---
# ==========================================
@bot.command(name="hs", aliases=["ws"])
@commands.cooldown(1, 10, commands.BucketType.user)
async def slots(ctx, amount_str: str):
    user_id = str(ctx.author.id)
    amount = get_bet_amount(user_id, amount_str)
    if not amount or amount <= 0:
        return await ctx.send("Geçersiz miktar kanka! Örnek: `hs 1000` veya `ws all`")
    current_bal = get_balance(user_id)
    if current_bal < amount:
        return await ctx.send("Yetersiz bakiye kanka!")

    username = ctx.author.name
    fruits = ["🍇", "🍈", "🍉", "🍊", "🍌", "🍍", "🍎", "🍒", "🍓", "🥝"]

    spin_embed = discord.Embed(
        description=f"**SLOTS**\n"
                    f"🔄 | 🔄 | 🔄\n"
                    f"👤 {username} bet 🪙 {amount:,}",
        color=discord.Color.dark_theme()
    )
    msg = await ctx.send(embed=spin_embed)
    await asyncio.sleep(0.8)

    forced_win = check_and_update_pity(user_id)
    win_chance = forced_win or random.choices([True, False], weights=[5, 95], k=1)[0]

    if win_chance:
        chosen_fruit = random.choice(fruits)
        match_type = random.choice(["triple", "double1", "double2"])
        
        if match_type == "triple":
            s1 = s2 = s3 = chosen_fruit
        elif match_type == "double1":
            s1 = s2 = chosen_fruit
            s3 = random.choice([f for f in fruits if f != chosen_fruit])
        else:
            s2 = s3 = chosen_fruit
            s1 = random.choice([f for f in fruits if f != chosen_fruit])
    else:
        s1 = fruits[0]
        s2 = fruits[1]
        s3 = fruits[2]
        while s1 == s2 or s2 == s3 or s1 == s3:
            s1 = random.choice(fruits)
            s2 = random.choice(fruits)
            s3 = random.choice(fruits)

    if s1 == s2 == s3:
        won = amount * 5
        update_balance(user_id, current_bal + won)
        result_text = f"👑 Jackpot! Üçlü eşleşme (+{won:,} 🪙)"
        embed_color = discord.Color.gold()
    elif s1 == s2 or s2 == s3:
        won = amount * 2
        update_balance(user_id, current_bal + won)
        result_text = f"✨ Kazandın! İkili eşleşme (+{won:,} 🪙)"
        embed_color = discord.Color.green()
    else:
        update_balance(user_id, current_bal - amount)
        result_text = f"😢 Kaybettin, sağlık olsun! (-{amount:,} 🪙)"
        embed_color = discord.Color.red()

    final_embed = discord.Embed(
        description=f"**SLOTS**\n"
                    f"{s1} | {s2} | {s3}\n\n"
                    f"👤 {username} bet 🪙 {amount:,}\n"
                    f"📢 {result_text}",
        color=embed_color
    )
    await msg.edit(embed=final_embed)

# ==========================================
# --- BLACKJACK (HJ) - 20'de 1 Kesin Kazanma ---
# ==========================================
class BlackjackView(discord.ui.View):
    def __init__(self, ctx, user_id, amount, forced_win):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.user_id = user_id
        self.amount = amount
        
        self.cards = [("🂡", 11), ("🂢", 2), ("🂣", 3), ("🂤", 4), ("🂥", 5), ("🂦", 6), ("🂧", 7), ("🂨", 8), ("🂩", 9), ("🂪", 10), ("🂫", 10), ("🂭", 10), ("🂮", 10),
                     ("🃁", 11), ("🃂", 2), ("🃃", 3), ("🃄", 4), ("🃅", 5), ("🃆", 6), ("🃇", 7), ("🃈", 8), ("🃉", 9), ("🃊", 10), ("🃋", 10), ("🃍", 10), ("🃎", 10)]
        
        if forced_win:
            # 20. elde kesin kazanma garantisi için avantajlı el
            self.player_hand = [("🂪", 10), ("🂩", 9)] # 19 başlangıç
            self.dealer_hand = [("🂥", 5), ("🂤", 4)]  # 9 başlangıç (Krupiye zayıf)
        else:
            self.player_hand = [random.choice(self.cards), random.choice(self.cards)]
            self.dealer_hand = [random.choice(self.cards), random.choice(self.cards)]

    def get_score(self, hand):
        score = sum(card[1] for card in hand)
        aces = sum(1 for card in hand if card[1] == 11)
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score

    def build_embed(self, status_text, color=discord.Color.red()):
        p_score = self.get_score(self.player_hand)
        d_score = self.get_score(self.dealer_hand)
        
        p_cards_str = " ".join([card[0] for card in self.player_hand])
        d_cards_str = " ".join([card[0] for card in self.dealer_hand])
        
        username = self.ctx.author.name
        
        embed = discord.Embed(
            description=f"🪙 **{username}, you bet {self.amount:,} to play blackjack**\n\n"
                        f"Dealer **[{d_score}]**\n{d_cards_str}\n\n"
                        f"{username} **[{p_score}]**\n{p_cards_str}\n\n"
                        f"{status_text}",
            color=color
        )
        return embed

    @discord.ui.button(emoji="👊", style=discord.ButtonStyle.blurple)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            return await interaction.response.send_message("Bu oyun senin değil kanka!", ephemeral=True)
        
        self.player_hand.append(random.choice(self.cards))
        p_score = self.get_score(self.player_hand)
        
        if p_score > 21:
            current_bal = get_balance(self.user_id)
            update_balance(self.user_id, current_bal - self.amount)
            text = f"🎲 ~ **You lost {self.amount:,} cowoncy!**"
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=self.build_embed(text, discord.Color.dark_red()), view=self)
            self.stop()
        else:
            await interaction.response.edit_message(embed=self.build_embed("🎲 Kart çekildi... Seçimini yap!"), view=self)

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            return await interaction.response.send_message("Bu oyun senin değil kanka!", ephemeral=True)
        
        p_score = self.get_score(self.player_hand)
        d_score = self.get_score(self.dealer_hand)
        
        while d_score < 17:
            self.dealer_hand.append(random.choice(self.cards))
            d_score = self.get_score(self.dealer_hand)
            
        current_bal = get_balance(self.user_id)
        if d_score > 21 or p_score > d_score:
            update_balance(self.user_id, current_bal + self.amount)
            text = f"🎉 **Masayı yendin ve kazandın! +{self.amount * 2:,} 🪙**"
            embed_color = discord.Color.green()
        elif p_score == d_score:
            text = f"🤝 **Berabere! Paran iade edildi.**"
            embed_color = discord.Color.gold()
        else:
            update_balance(self.user_id, current_bal - self.amount)
            text = f"🎲 ~ **You lost {self.amount:,} cowoncy!**"
            embed_color = discord.Color.dark_red()
        
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(embed=self.build_embed(text, embed_color), view=self)
        self.stop()

@bot.command(name="hj")
@commands.cooldown(1, 10, commands.BucketType.user)
async def hj_game(ctx, amount_str: str):
    user_id = str(ctx.author.id)
    amount = get_bet_amount(user_id, amount_str)
    if not amount or amount <= 0:
        return await ctx.send("Geçersiz miktar kanka! Örnek: `hj 1000`")
    if get_balance(user_id) < amount:
        return await ctx.send("Yetersiz bakiye kanka!")

    forced_win = check_and_update_pity(user_id)
    view = BlackjackView(ctx, user_id, amount, forced_win)
    initial_text = f"🎲 Kartlar dağıtıldı! Kart çekmek için 👊, durmak için 🛑 butonuna bas."
    await ctx.send(embed=view.build_embed(initial_text), view=view)

@bot.command(name="h")
async def balance(ctx):
    bal = get_balance(ctx.author.id)
    await ctx.send(f"🪙 **{ctx.author.name}**, cüzdanında **{bal:,}** var.")

# --- HATA YÖNETİMİ (Cooldown ve Komut Bulunamadı) ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CommandOnCooldown):
        remaining = int(error.retry_after)
        await ctx.send(f"⏳ Çok hızlı oynuyorsun kanka! Tekrar oynamak için **{remaining} saniye** beklemelisin.", delete_after=5)

# --- BİLGİ KOMUTU (!hbilgi) ---
@bot.command(name="hbilgi")
async def hbilgi(ctx):
    embed = discord.Embed(
        title="🤖 HelperX Ekonomi & Eğlence Botu",
        description="Sunucumuzun resmi ekonomi botudur. Paranı katlayabilir, oyunlar oynayabilir ve sıralamada yükselebilirsin kanka!",
        color=discord.Color.blue()
    )
    embed.add_field(name="💰 Ekonomi Komutları", value="`!h` - Cüzdanını görürsün\n`!daily` - Günlük ödülünü alırsın\n`!hpay` - Başkasına para gönderirsin\n`!lb` - Servet sıralamasına bakarsın", inline=False)
    embed.add_field(name="🎲 Kumar & Şans Oyunları (10sn Cooldown)", value="`!hf` - Coinflip (Yazı/Tura)\n`!hs` (veya `!ws`) - Slots\n`!hj` - Blackjack\n`!rulet` - Gerçek Rulet (Animasyonlu)\n`!kasa` - Kasa açma", inline=False)
    embed.add_field(name="🛠️ Yönetici Komutları", value="`!add` - Para eklersin\n`!hparasil` - Para silersin\n`!sil` - Mesaj temizlersin", inline=False)
    embed.set_footer(text="HelperX ile iyi eğlenceler dileriz!")
    await ctx.send(embed=embed)

# --- TEST KOMUTU ---
@bot.command()
async def hdeneme(ctx):
    user_id = str(ctx.author.id)
    para = get_balance(user_id)
    await ctx.send(f"Deneme başarılı kanka! Cüzdanındaki güncel para: **{para:,}** coin.")

# --- YENİ EKLENEN DENEME KOMUTU (hdenemekomutu3) ---
@bot.command(name="hdenemekomutu3")
async def hdenemekomutu3(ctx):
    user_id = str(ctx.author.id)
    bal = get_balance(user_id)
    bank = get_bank(user_id)
    await ctx.send(f"🔍 **{ctx.author.name}**, veritabanı kontrolü başarılı (Komut 3)!\n🪙 Cüzdan: **{bal:,}** coin\n🏦 Banka: **{bank:,}** coin")

bot.run(os.getenv("DISCORD_TOKEN", "TOKEN_BURAYA")) 
