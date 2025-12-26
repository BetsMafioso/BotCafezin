import discord
from discord.ext import commands
import yt_dlp
import asyncio
import time
import os
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

PREFIX = "!"
FFMPEG_PATH = "ffmpeg"
MUSIC_CHANNEL_ID = 1187549593341268019

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# =========================
# UTIL
# =========================

def format_time(seconds):
    if seconds is None:
        return "Ao vivo"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

# =========================
# ESTADO
# =========================

class MusicState:
    def __init__(self):
        self.queue = []
        self.history = []
        self.current = None

        self.loop_song = False
        self.loop_queue = False

        self.channel = None
        self.player_message = None
        self.start_time = None
        self.messages = []
        self.update_task = None

states = {}

def get_state(guild_id):
    if guild_id not in states:
        states[guild_id] = MusicState()
    return states[guild_id]

# =========================
# YTDLP / FFMPEG
# =========================

ytdlp_opts = {
    "format": "bestaudio/best",
    "default_search": "ytsearch",
    "quiet": True,
}

ffmpeg_opts = {
    "executable": FFMPEG_PATH,
    "options": "-vn"
}

# =========================
# EMBED
# =========================

def build_embed(state):
    url, title, thumb, duration = state.current
    elapsed = time.time() - state.start_time if state.start_time else 0

    embed = discord.Embed(
        title="🎶 Tocando agora",
        description=f"**{title}**",
        color=discord.Color.green()
    )

    embed.set_thumbnail(url=thumb)

    embed.add_field(
        name="⏱ Tempo",
        value=f"{format_time(elapsed)} / {format_time(duration)}",
        inline=False
    )

    embed.add_field(
        name="🔁 Música",
        value="Ligado" if state.loop_song else "Desligado",
        inline=True
    )

    embed.add_field(
        name="🔁 Playlist",
        value="Ligado" if state.loop_queue else "Desligado",
        inline=True
    )

    return embed

# =========================
# ATUALIZAR TEMPO
# =========================

async def update_embed_loop(guild):
    state = get_state(guild.id)
    while state.current and guild.voice_client and guild.voice_client.is_playing():
        try:
            await state.player_message.edit(embed=build_embed(state))
        except:
            pass
        await asyncio.sleep(5)

# =========================
# LIMPEZA
# =========================

async def cleanup(state):
    if state.update_task:
        state.update_task.cancel()

    for msg in state.messages:
        try:
            await msg.delete()
        except:
            pass

    state.queue.clear()
    state.history.clear()
    state.current = None
    state.loop_song = False
    state.loop_queue = False
    state.messages.clear()
    state.player_message = None

# =========================
# PLAYER
# =========================

async def play_next(guild):
    state = get_state(guild.id)
    vc = guild.voice_client

    if not vc or not vc.is_connected():
        return

    if state.loop_song and state.current:
        next_song = state.current
    else:
        if not state.queue:
            if state.loop_queue and state.history:
                state.queue = state.history.copy()
                state.history.clear()
            else:
                await cleanup(state)
                return
        next_song = state.queue.pop(0)

    state.current = next_song
    state.history.append(next_song)
    state.start_time = time.time()

    url, _, _, _ = state.current

    vc.play(
        discord.FFmpegPCMAudio(url, **ffmpeg_opts),
        after=lambda _: asyncio.run_coroutine_threadsafe(
            play_next(guild), bot.loop
        )
    )

    if state.player_message:
        try:
            await state.player_message.delete()
        except:
            pass

    state.player_message = await state.channel.send(
        embed=build_embed(state),
        view=MusicControls(guild)
    )
    state.messages.append(state.player_message)

    state.update_task = bot.loop.create_task(update_embed_loop(guild))

# =========================
# BOTÕES
# =========================

class MusicControls(discord.ui.View):
    timeout = None

    def __init__(self, guild):
        super().__init__()
        self.guild = guild

    @discord.ui.button(emoji="⏯", style=discord.ButtonStyle.gray)
    async def pause(self, interaction, _):
        await interaction.response.defer()
        vc = self.guild.voice_client
        if vc.is_playing():
            vc.pause()
        else:
            vc.resume()

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction, _):
        await interaction.response.defer()
        self.guild.voice_client.stop()

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.green)
    async def loop_song(self, interaction, _):
        await interaction.response.defer()
        state = get_state(self.guild.id)
        state.loop_song = not state.loop_song
        await state.player_message.edit(embed=build_embed(state), view=self)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.red)
    async def stop(self, interaction, _):
        await interaction.response.defer()
        state = get_state(self.guild.id)
        await cleanup(state)
        await self.guild.voice_client.disconnect()

# =========================
# COMANDOS
# =========================

@bot.command()
async def play(ctx, *, query):
    if ctx.channel.id != MUSIC_CHANNEL_ID:
        embed = discord.Embed(
            title="❌ Comando não permitido aqui",
            description=f"Use <#{MUSIC_CHANNEL_ID}> para comandos de música",
            color=discord.Color.red()
        )

        embed.set_footer(
            text="🎧 Para o sistema de música • Use o canal correto",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )

        return await ctx.send(embed=embed)

    if not ctx.author.voice:
        return await ctx.send("❌ Entre em um canal de voz")

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    state = get_state(ctx.guild.id)
    state.channel = ctx.channel
    state.messages.append(ctx.message)

    with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
        info = ydl.extract_info(query, download=False)

        if "entries" in info:
            for e in info["entries"]:
                state.queue.append((e["url"], e["title"], e.get("thumbnail"), e.get("duration")))
        else:
            state.queue.append((info["url"], info["title"], info.get("thumbnail"), info.get("duration")))

    if not ctx.voice_client.is_playing():
        await play_next(ctx.guild)
    else:
        msg = await ctx.send("➕ Música(s) adicionada(s) à fila")
        state.messages.append(msg)

@bot.command()
async def loop(ctx):
    state = get_state(ctx.guild.id)

    if len(state.queue) < 1:
        return await ctx.send("❌ Loop só funciona com playlist")

    state.loop_queue = not state.loop_queue
    await ctx.send(f"🔁 Loop da playlist {'ativado' if state.loop_queue else 'desativado'}")

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    print(f"🎧 Bot online como {bot.user}")

bot.run(TOKEN)
