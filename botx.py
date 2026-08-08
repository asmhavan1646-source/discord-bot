import asyncio
import datetime
import json
import os
import random
import time
import discord
from discord.ext import commands, tasks
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="", intents=intents, case_insensitive=True)

# --- TEK KANAL ID AYARI ---
ALLOWED_CHANNEL_ID = 1535569350403297381  # Botun çalışacağı kanalın ID'si

@bot.check
async def globally_block_channels(ctx):
    if ctx.channel.id != ALLOWED_CHANNEL_ID:
        # İstersen uyarı mesajını açabilirsin, şimdilik sessizce görmezden geliyor
        return False
    return True

# --- VERİLERİ DOSYADA SAKLAMA SİSTEMİ ---
DATA_FILE = "economy_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            balances = {int(k): v for k, v in data.get("balances", {}).items()}
            banks = {int(k): v for k, v in data.get("banks", {}).items()}
            streaks = {int(k): v for k, v in data.get("streaks", {}).items()}
            return balances, banks, streaks
    return {}, {}, {}

def save_data():
    data = {
        "balances": user_balances,
        "banks": user_banks,
        "streaks": daily_streaks
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_balances, user_banks, daily_streaks = load_data()
daily_cooldowns = {}
crime_cooldowns = {}
hpay_cooldowns = {}

def get_balance(user_id):
    if user_id not in user_balances:
        user_balances[user_id] = 50000
        save_data()
    return user_balances[user_id]

def get_bank(user_id):
    if user_id not in user_banks:
        user_banks[user_id] = 0
        save_data()
    return user_banks[user_id]

def get_bet_amount(user_id, amount_str):
    balance = get_balance(user_id)
    if amount_str.lower() == "all":
        return balance
    try:
        amount = int(amount_str)
        return amount
    except:
        return None

# --- OTOMATİK FAİZ DÖNGÜSÜ (Her 1 saate bir %10 faiz) ---
@tasks.loop(hours=1)
async def bank_interest():
    for user_id in list(user_banks.keys()):
        current_bank = user_banks[user_id]
        if current_bank > 0:
            added_interest = int(current_bank * 0.10)
            user_banks[user_id] += added_interest
    save_data()

@bot.event
async def on_ready():
    print(f"Bot aktif: {bot.user.name}")
    if not bank_interest.is_running():
        bank_interest.start()

# --- GÜNLÜK ÖDÜL ---
@bot.command(name="daily")
async def daily(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.now()
    
    if user_id not in daily_streaks:
        daily_streaks[user_id] = 1
    
    if user_id in daily_cooldowns:
        last_time = daily_cooldowns[user_id]
        if (now - last_time).total_seconds() < 86400:
            remaining = datetime.timedelta(seconds=86400) - (now - last_time)
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return await ctx.send(f"⏳ | **{ctx.author.name}**, bir sonraki ödülüne **{hours} saat {minutes} dakika** var.")

    reward = daily_streaks[user_id] * 5000
    user_balances[user_id] = get_balance(user_id) + reward
    daily_streaks[user_id] += 1
    daily_cooldowns[user_id] = now
    save_data()
    
    await ctx.send(f"🎁 **{ctx.author.name}**, günlük ödülün: **{reward:,} 🪙**. Bir sonraki ödülün **{(daily_streaks[user_id]) * 5000:,} 🪙** olacak!")

# --- SOYGUN (CRIME) ---
@bot.command(name="crime")
async def crime(ctx):
    user_id = ctx.author.id
    now = datetime.datetime.now()
    
    is_owner = any(role.name.lower() == "owner" for role in ctx.author.roles)
    
    if not is_owner:
        if user_id in crime_cooldowns:
            last_time = crime_cooldowns[user_id]
            if (now - last_time).total_seconds() < 7200:
                remaining = datetime.timedelta(seconds=7200) - (now - last_time)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return await ctx.send(f"⏳ | Polisler peşinde! Saklanmak için **{hours} saat {minutes} dakika** beklemelisin.")
        crime_cooldowns[user_id] = now
            
    owner_text = " (Owner Modu: Sınır Yok!)" if is_owner else ""
    
    if is_owner:
        stolen = 100000
        user_balances[user_id] = get_balance(user_id) + stolen
        save_data()
        return await ctx.send(f"💎 **OWNER EFSANE VURGUN!** Kral devleti soydun! Cüzdanına **{stolen:,} 🪙** eklendi!{owner_text}")

    success = random.choice([True, False])
    
    if success:
        is_jackpot = random.choices([True, False], weights=[10, 90], k=1)[0]
        
        if is_jackpot:
            stolen = 100000
            user_balances[user_id] = get_balance(user_id) + stolen
            await ctx.send(f"💎 **EFSANE VURGUN!** Büyük bankayı soydun! Cüzdanına **{stolen:,} 🪙** eklendi!")
        else:
            stolen = random.randint(20000, 50000)
            user_balances[user_id] = get_balance(user_id) + stolen
            await ctx.send(f"🥷 Süper soygun! Kasayı soyup kaçtın: **{stolen:,} 🪙**")
    else:
        fine = random.randint(10000, 25000)
        current_bal = get_balance(user_id)
        lost = min(fine, current_bal)
        user_balances[user_id] = current_bal - lost
        await ctx.send(f"🚨 Polis bastı! Ceza olarak **{lost:,} 🪙** kaptırdın!")
    
    save_data()

# --- ŞANSLI ÇARK (ROULETTE / CARK) ---
@bot.command(name="roulette", aliases=["cark"])
async def roulette(ctx, color: str, amount_str: str):
    user_id = ctx.author.id
    color = color.lower()
    
    if color not in ["kırmızı", "siyah", "yeşil"]:
        return await ctx.send("Renk seçimi yanlış kanka! Şunlardan birini yazmalısın: `kırmızı`, `siyah`, `yeşil`")
        
    amount = get_bet_amount(user_id, amount_str)
    if amount is None or amount <= 0 or get_balance(user_id) < amount:
        return await ctx.send("Geçersiz miktar veya yetersiz bakiye kanka!")
        
    msg = await ctx.send("🎡 Şans çarkı dönüyor...")
    await asyncio.sleep(1.5)
    
    outcome = random.choices(["kırmızı", "siyah", "yeşil"], weights=[45, 45, 10], k=1)[0]
    
    if outcome == color:
        multiplier = 10 if outcome == "yeşil" else 2
        won_amount = amount * multiplier
        user_balances[user_id] += won_amount
        await msg.edit(content=f"🎯 Çark durdu: **{outcome.upper()}**! Tebrikler kazandın! +**{won_amount:,} 🪙**")
    else:
        user_balances[user_id] -= amount
        await msg.edit(content=f"😢 Çark durdu: **{outcome.upper()}** geldi. Kaybettin kanka! -**{amount:,} 🪙**")
    
    save_data()

# --- KASA AÇMA SİSTEMİ ---
@bot.command(name="kasa", aliases=["lootbox"])
async def open_box(ctx, box_type: str = None):
    user_id = ctx.author.id
    
    if not box_type or box_type.lower() not in ["normal", "lüks", "luks", "mega"]:
        return await ctx.send("Hangi kasayı açmak istiyorsun kanka? Seçenekler:\n• `kasa normal` (10.000 🪙)\n• `kasa lüks` (50.000 🪙)\n• `kasa mega` (100.000 🪙)")
        
    box_type = box_type.lower()
    
    if box_type == "normal":
        price = 10000
    elif box_type in ["lüks", "luks"]:
        box_type = "lüks"
        price = 50000
    else:
        price = 100000
        
    if get_balance(user_id) < price:
        return await ctx.send(f"Yetersiz bakiye kanka! Bu kasayı açmak için **{price:,} 🪙** gerekiyor.")
        
    user_balances[user_id] -= price
    
    msg = await ctx.send("📦 Kasa açılıyor, içerisi taranıyor...")
    await asyncio.sleep(1.5)
    
    if box_type == "normal":
        reward = random.choices(
            [random.randint(10000, 20000), random.randint(20001, 35000), random.randint(35001, 50000)],
            weights=[60, 30, 10], k=1
        )[0]
    elif box_type == "lüks":
        reward = random.choices(
            [random.randint(50000, 65000), random.randint(65001, 85000), random.randint(85001, 100000)],
            weights=[60, 30, 10], k=1
        )[0]
    else:
        reward = random.choices(
            [random.randint(100000, 130000), random.randint(130001, 180000), random.randint(180001, 250000)],
            weights=[60, 30, 10], k=1
        )[0]
        
    user_balances[user_id] += reward
    save_data()
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
    user_id = ctx.author.id
    bal = get_balance(user_id)
    amount = bal if amount_str.lower() == "all" else int(amount_str) if amount_str.isdigit() else 0
    
    if amount <= 0 or bal < amount:
        return await ctx.send("Geçersiz miktar veya yetersiz cüzdan!")
        
    user_balances[user_id] -= amount
    user_banks[user_id] = get_bank(user_id) + amount
    save_data()
    await ctx.send(f"🏦 Cüzdanından **{amount:,} 🪙** bankaya yatırıldı.")

# --- BANKA: PARA ÇEKME (WITHDRAW) ---
@bot.command(name="withdraw")
async def withdraw(ctx, amount_str: str):
    user_id = ctx.author.id
    bank = get_bank(user_id)
    amount = bank if amount_str.lower() == "all" else int(amount_str) if amount_str.isdigit() else 0
    
    if amount <= 0 or bank < amount:
        return await ctx.send("Geçersiz miktar veya yetersiz banka bakiyesi!")
        
    user_banks[user_id] -= amount
    user_balances[user_id] = get_balance(user_id) + amount
    save_data()
    await ctx.send(f"💸 Bankadan **{amount:,} 🪙** çekildi.")

# --- SERVET SIRALAMASI (LB) ---
@bot.command(name="lb")
async def leaderboard(ctx):
    all_users = set(list(user_balances.keys()) + list(user_banks.keys()))
    if not all_users:
        return await ctx.send("Henüz sıralamada kimse yok!")
        
    net_worths = {uid: get_balance(uid) + get_bank(uid) for uid in all_users}
    sorted_users = sorted(net_worths.items(), key=lambda item: item[1], reverse=True)[:10]
    
    embed = discord.Embed(title="🏆 HelperX - Servet Sıralaması", color=discord.Color.gold())
    desc = "".join([f"**{idx}.** <@!{uid}> — **{total:,}** 🪙\n" for idx, (uid, total) in enumerate(sorted_users, 1)])
    embed.description = desc
    await ctx.send(embed=embed)

# --- MAĞAZA (SHOP) & BUY ---
@bot.command(name="shop")
async def shop(ctx):
    embed = discord.Embed(title="🛒 HelperX Mağaza", description="Paranı harcayarak özel rol alabilirsin!", color=discord.Color.blue())
    embed.add_field(name="VIP Rolü", value="Fiyat: **10,000,000 🪙**\nKomut: `buy vip`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="buy")
async def buy(ctx, item: str = None):
    if not item or item.lower() != "vip":
        return await ctx.send("Mağazada sadece `buy vip` ürünü bulunuyor!")
        
    user_id = ctx.author.id
    bal = get_balance(user_id)
    price = 1000000000
    
    if bal < price:
        return await ctx.send(f"Yetersiz bakiye! VIP için **{price:,} 🪙** gerekiyor.")
        
    user_balances[user_id] -= price
    save_data()
    
    role = discord.utils.get(ctx.guild.roles, name="VIP")
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"🎉 Tebrikler! **10,000,000 🪙** ödeyerek VIP rolünü aldın.")
    else:
        await ctx.send("Paran çekildi fakat sunucuda 'VIP' rolü bulunamadı!")

# --- PROFİL ---
@bot.command(name="profile")
async def profile(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_id = target.id
    bal = get_balance(user_id)
    bank = get_bank(user_id)
    total = bal + bank
    streak = daily_streaks.get(user_id, 0)
    
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
    user_balances[ctx.author.id] = get_balance(ctx.author.id) + amount
    save_data()
    await ctx.send(f"👑 Cüzdanına **{amount:,}** eklendi!")

@bot.command(name="hpay")
async def hpay(ctx, member: discord.Member, amount: int):
    sender_id = ctx.author.id
    receiver_id = member.id
    
    if sender_id == receiver_id:
        await ctx.send("Kendine humoral gönderemezsin kanka!")
        return

    if amount <= 0:
        await ctx.send("Gönderilecek miktar 0'dan büyük olmalı!")
        return

    if amount > 1000000:
        await ctx.send("Tek seferde en fazla **1.000.000 🪙** gönderebilirsin!")
        return

    current_time = time.time()
    if sender_id in hpay_cooldowns:
        last_time, sent_total = hpay_cooldowns[sender_id]
        if current_time - last_time < 3600:
            if sent_total + amount > 1000000:
                left_time = int(3600 - (current_time - last_time))
                dakika = left_time // 60
                await ctx.send(f"Saatlik 1.000.000 🪙 limitine ulaştın! Tekrar para göndermek için **{dakika} dakika** beklemelisin.")
                return
            else:
                hpay_cooldowns[sender_id] = (last_time, sent_total + amount)
        else:
            hpay_cooldowns[sender_id] = (current_time, amount)
    else:
        hpay_cooldowns[sender_id] = (current_time, amount)

    sender_wallet = get_balance(sender_id)
    if sender_wallet < amount:
        await ctx.send("Cüzdanında transfer için yeterli para yok!")
        return

    user_balances[sender_id] = sender_wallet - amount
    user_balances[receiver_id] = get_balance(receiver_id) + amount
    save_data()
    
    await ctx.send(f"💸 **{member.name}** kişisine **{amount:,} 🪙** gönderildi!")

# ==========================================
# --- COINFLIP (HF) - %50 KAZANMA ORANI ---
# ==========================================

@bot.command(name="hf")
async def coinflip(ctx, amount_str: str):
    user_id = ctx.author.id
    amount = get_bet_amount(user_id, amount_str)
    if not amount or amount <= 0:
        return await ctx.send("Geçersiz miktar kanka! Örnek: `hf 1000`")
    if get_balance(user_id) < amount:
        return await ctx.send("Yetersiz bakiye kanka!")

    win_chance = random.choices([True, False], weights=[50, 50], k=1)[0]

    if win_chance:
        user_balances[user_id] += amount
        await ctx.send(f"🪙 **{ctx.author.name}** kazandı! +**{amount * 2:,} 🪙**")
    else:
        user_balances[user_id] -= amount
        await ctx.send(f"🪙 **{ctx.author.name}** kaybetti! -**{amount:,} 🪙** :c")
    
    save_data()

# ==========================================
# --- SLOTS (HS / WS) - %50 KAZANMA ORANI ---
# ==========================================

@bot.command(name="hs", aliases=["ws"])
async def slots(ctx, amount_str: str):
    user_id = ctx.author.id
    amount = get_bet_amount(user_id, amount_str)
    if not amount or amount <= 0:
        return await ctx.send("Geçersiz miktar kanka! Örnek: `hs 1000` veya `ws all`")
    if get_balance(user_id) < amount:
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

    win_chance = random.choices([True, False], weights=[50, 50], k=1)[0]

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
        user_balances[user_id] += won
        result_text = f"👑 Jackpot! Üçlü eşleşme (+{won:,} 🪙)"
        embed_color = discord.Color.gold()
    elif s1 == s2 or s2 == s3:
        won = amount * 2
        user_balances[user_id] += won
        result_text = f"✨ Kazandın! İkili eşleşme (+{won:,} 🪙)"
        embed_color = discord.Color.green()
    else:
        user_balances[user_id] -= amount
        result_text = f"😢 Kaybettin, sağlık olsun! (-{amount:,} 🪙)"
        embed_color = discord.Color.red()

    save_data()

    final_embed = discord.Embed(
        description=f"**SLOTS**\n"
                    f"{s1} | {s2} | {s3}\n\n"
                    f"👤 {username} bet 🪙 {amount:,}\n"
                    f"📢 {result_text}",
        color=embed_color
    )
    await msg.edit(embed=final_embed)

# ==========================================
# --- BLACKJACK (HJ) - %50 KAZANMA ORANI ---
# ==========================================

class BlackjackView(discord.ui.View):
    def __init__(self, ctx, user_id, amount):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.user_id = user_id
        self.amount = amount
        
        self.cards = [("🂡", 11), ("🂢", 2), ("🂣", 3), ("🂤", 4), ("🂥", 5), ("🂦", 6), ("🂧", 7), ("🂨", 8), ("🂩", 9), ("🂪", 10), ("🂫", 10), ("🂭", 10), ("🂮", 10),
                      ("🃁", 11), ("🃂", 2), ("🃃", 3), ("🃄", 4), ("🃅", 5), ("🃆", 6), ("🃇", 7), ("🃈", 8), ("🃉", 9), ("🃊", 10), ("🃋", 10), ("🃍", 10), ("🃎", 10)]
        
        win_bias = random.choices([True, False], weights=[50, 50], k=1)[0]
        if win_bias:
            self.player_hand = [("🂪", 10), ("🂫", 10)]
            self.dealer_hand = [("🂦", 6), ("🂤", 4)]
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
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Bu oyun senin değil kanka!", ephemeral=True)
        
        self.player_hand.append(random.choice(self.cards))
        p_score = self.get_score(self.player_hand)
        
        if p_score > 21:
            user_balances[self.user_id] -= self.amount
            save_data()
            text = f"🎲 ~ **You lost {self.amount:,} cowoncy!**"
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=self.build_embed(text, discord.Color.dark_red()), view=self)
            self.stop()
        else:
            await interaction.response.edit_message(embed=self.build_embed("🎲 Kart çekildi... Seçimini yap!"), view=self)

    @discord.ui.button(emoji="🛑", style=discord.ButtonStyle.danger)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Bu oyun senin değil kanka!", ephemeral=True)
        
        p_score = self.get_score(self.player_hand)
        d_score = self.get_score(self.dealer_hand)
        
        while d_score < 17:
            self.dealer_hand.append(random.choice(self.cards))
            d_score = self.get_score(self.dealer_hand)
            
        if d_score > 21 or p_score > d_score:
            user_balances[self.user_id] += self.amount
            text = f"🎉 **Masayı yendin ve kazandın! +{self.amount * 2:,} 🪙**"
            embed_color = discord.Color.green()
        elif p_score == d_score:
            text = f"🤝 **Berabere! Paran iade edildi.**"
            embed_color = discord.Color.gold()
        else:
            user_balances[self.user_id] -= self.amount
            text = f"🎲 ~ **You lost {self.amount:,} cowoncy!**"
            embed_color = discord.Color.dark_red()
            
        save_data()
            
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(embed=self.build_embed(text, embed_color), view=self)
        self.stop()

@bot.command(name="hj")
async def hj_game(ctx, amount_str: str):
    user_id = ctx.author.id
    amount = get_bet_amount(user_id, amount_str)
    if not amount or amount <= 0:
        return await ctx.send("Geçersiz miktar kanka! Örnek: `hj 1000`")
    if get_balance(user_id) < amount:
        return await ctx.send("Yetersiz bakiye kanka!")

    view = BlackjackView(ctx, user_id, amount)
    initial_text = f"🎲 Kartlar dağıtıldı! Kart çekmek için 👊, durmak için 🛑 butonuna bas."
    await ctx.send(embed=view.build_embed(initial_text), view=view)

@bot.command(name="h")
async def balance(ctx):
    bal = get_balance(ctx.author.id)
    await ctx.send(f"🪙 **{ctx.author.name}**, cüzdanında **{bal:,}** var.")

bot.run(os.getenv("DISCORD_TOKEN"))
