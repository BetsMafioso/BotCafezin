import discord
from discord.ext import commands
import yt_dlp
import asyncio
import time
import os
import tempfile
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

def error_embed(title, desc):
    return discord.Embed(
        title=f"❌ {title}",
        description=desc,
        color=discord.Color.red()
    )

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
# YTDLP CONFIG
# =========================

def ytdlp_base_opts():
    opts = {
        "format": "bestaudio[protocol!=m3u8]/bestaudio/best",
        "quiet": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "source_address": "0.0.0.0",
        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
                "skip": ["dash", "hls"]
            }
        }
    }

    # =========================
    # YOUTUBE COOKIES (OPCIONAL)
    # =========================
    cookies = os.getenv("YTDLP_COOKIES")
    if cookies:
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.write(cookies.encode("utf-8"))
        tmp.close()
        opts["cookiefile"] = tmp.name

    return opts



def ytdlp_soundcloud_opts():
    opts = ytdlp_base_opts()
    opts["default_search"] = "scsearch"
    return opts


def ytdlp_youtube_opts():
    opts = ytdlp_base_opts()
    opts["default_search"] = "ytsearch"
    return opts

ffmpeg_opts = {
    "executable": FFMPEG_PATH,
    "before_options": (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-protocol_whitelist file,http,https,tcp,tls,crypto "
        "-allowed_extensions ALL"
    ),
    "options": "-vn"
}

# =========================
# EMBED PLAYER
# =========================

def build_embed(state):
    url, title, thumb, duration = state.current
    elapsed = time.time() - state.start_time if state.start_time else 0

    embed = discord.Embed(
        title="🎶 Tocando agora",
        description=f"**{title}**",
        color=discord.Color.green()
    )

    if thumb:
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
# UPDATE EMBED
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
# CLEANUP
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
        song = state.current
    else:
        if not state.queue:
            if state.loop_queue and state.history:
                state.queue = state.history.copy()
                state.history.clear()
            else:
                await cleanup(state)
                return
        song = state.queue.pop(0)

    state.current = song
    state.history.append(song)
    state.start_time = time.time()

    url, _, _, _ = song

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
# CONTROLS
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
        vc.pause() if vc.is_playing() else vc.resume()

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
# COMMANDS
# =========================

@bot.command()
async def play(ctx, *, query):
    if ctx.channel.id != MUSIC_CHANNEL_ID:
        return await ctx.send(
            embed=error_embed(
                "Canal errado",
                f"Use <#{MUSIC_CHANNEL_ID}> para comandos de música 🎧"
            )
        )

    if not ctx.author.voice:
        return await ctx.send(embed=error_embed("Entre em um canal de voz", "Você precisa estar em um canal de voz."))

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    state = get_state(ctx.guild.id)
    state.channel = ctx.channel
    state.messages.append(ctx.message)

    info = None

    # 🔊 SoundCloud PRIMEIRO
    try:
        with yt_dlp.YoutubeDL(ytdlp_soundcloud_opts()) as ydl:
            info = ydl.extract_info(query, download=False)
    except:
        pass

    # ▶️ YouTube BACKUP
    if not info:
        try:
            with yt_dlp.YoutubeDL(ytdlp_youtube_opts()) as ydl:
                info = ydl.extract_info(query, download=False)
        except:
            return await ctx.send(
                embed=error_embed(
                    "Falha ao carregar",
                    "Não consegui tocar essa música nem pelo SoundCloud nem pelo YouTube 😢"
                )
            )

    if "entries" in info:
        for e in info["entries"]:
            if e:
                state.queue.append((e["url"], e["title"], e.get("thumbnail"), e.get("duration")))
    else:
        state.queue.append((info["url"], info["title"], info.get("thumbnail"), info.get("duration")))

    if not ctx.voice_client.is_playing():
        await play_next(ctx.guild)
    else:
        msg = await ctx.send("➕ Música adicionada à fila")
        state.messages.append(msg)

@bot.command()
async def loop(ctx):
    state = get_state(ctx.guild.id)

    if not state.queue:
        return await ctx.send(embed=error_embed("Loop inválido", "O loop só funciona com playlist."))

    state.loop_queue = not state.loop_queue
    await ctx.send(f"🔁 Loop da playlist {'ativado' if state.loop_queue else 'desativado'}")

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    print(f"🎧 Bot online como {bot.user}")

bot.run(TOKEN)
