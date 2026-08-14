import discord
from discord.ext import commands
from discord import app_commands, ui
import aiohttp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# ========== 設定 ==========
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ========== トークン検証 ==========
async def verify_token(user_token: str):
    url = "https://discord.com/api/v10/users/@me"
    headers = {"Authorization": user_token.strip()}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = f"{data.get('username')}#{data.get('discriminator', '0')}"
                    return True, username
                elif resp.status == 401:
                    return False, "❌ トークンが無効または期限切れ"
                else:
                    return False, f"❌ 確認エラー: ステータス{resp.status}"
    except Exception as e:
        return False, f"⚠️ 通信エラー: {str(e)[:40]}"


# ========== サーバー参加実行 ==========
async def join_server(token: str, invite_code: str):
    url = f"https://discord.com/api/v10/invites/{invite_code.strip()}"
    headers = {"Authorization": token.strip(), "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    guild = data.get("guild", {})
                    name = guild.get("name", "サーバー")
                    return True, f"✅ {name} に参加成功"
                elif resp.status == 401:
                    return False, "❌ トークン無効"
                elif resp.status == 403:
                    return False, "⚠️ 参加権限なし/制限中"
                elif resp.status == 429:
                    return False, "⏳ API制限（少し待って再試行）"
                elif resp.status in (304, 204):
                    return True, "✅ 既に参加済み"
                else:
                    return False, f"❌ エラー: ステータス{resp.status}"
    except Exception as e:
        return False, f"⚠️ 通信エラー: {str(e)[:40]}"


# ========== ② 招待・トークン一括入力フォーム ==========
class InviteForm(ui.Modal, title="🔗 一括参加 実行"):
    invite_code = ui.TextInput(
        label="招待コード",
        placeholder="例: abc123",
        required=True
    )
    token_list = ui.TextInput(
        label="⚠️ 参加させるトークン【絶対に本垢禁止】",
        style=discord.TextStyle.long,
        placeholder="❗ 捨て垢のトークンのみ使用してください。\n（1行に1つ貼り付け）\n捨て垢\n捨て垢2",
        required=True
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        tokens = [t.strip() for t in self.token_list.value.strip().splitlines() if t.strip()]
        code = self.invite_code.value.strip()

        if not tokens:
            await interaction.followup.send("⚠️ トークンが入力されていません。", ephemeral=True)
            return

        embed = discord.Embed(title="🔄 実行中…", color=0x3498DB)
        embed.add_field(name="招待コード", value=f"`{code}`", inline=False)
        embed.add_field(name="トークン数", value=f"{len(tokens)} 個", inline=False)
        status_msg = await interaction.followup.send(embed=embed, ephemeral=True)

        results = []
        success = 0
        for i, token in enumerate(tokens, 1):
            ok, msg = await join_server(token, code)
            if ok:
                success += 1
            results.append(f"[{i}] {msg}")
            await asyncio.sleep(0.1)

        result_text = "\n".join(results[:15])
        if len(results) > 15:
            result_text += f"\n…ほか {len(results)-15} 件"

        embed = discord.Embed(title="📊 実行結果", color=0x2ECC71 if success > 0 else 0xE74C3C)
        embed.add_field(name="招待コード", value=f"`{code}`", inline=False)
        embed.add_field(name="トークン数", value=f"{len(tokens)} 個", inline=False)
        embed.add_field(name="✅ 成功", value=f"{success} 個", inline=True)
        embed.add_field(name="❌ 失敗", value=f"{len(tokens)-success} 個", inline=True)
        embed.add_field(name="詳細", value=f"```\n{result_text}\n```", inline=False)

        await status_msg.edit(embed=embed)


# ========== ① 本人確認フォーム ==========
class VerifyForm(ui.Modal, title="🔐 本人確認：トークンを入力"):
    user_token = ui.TextInput(
        label="⚠️ 確認用トークン【絶対に本垢禁止】",
        style=discord.TextStyle.short,
        placeholder="❗ 捨て垢のトークンを入力してください",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        token = self.user_token.value.strip()
        ok, msg = await verify_token(token)

        if not ok:
            await interaction.followup.send(f"❌ 確認失敗:\n{msg}", ephemeral=True)
            return

        embed = discord.Embed(title=f"✅ 確認OK: {msg}", color=0x2ECC71)
        embed.add_field(name="次へ", value="下のボタンから招待設定を入力してください。", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True, view=NextView())


# ========== 2段階目ボタン ==========
class NextView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔗 招待コード・トークン入力へ", style=discord.ButtonStyle.primary, custom_id="open_invite_form")
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(InviteForm())


# ========== 最初のパネルボタン ==========
class MainView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔐 開始：トークンを入力", style=discord.ButtonStyle.primary, custom_id="start_verify_modal")
    async def start_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VerifyForm())


# ========== Bot起動・コマンド同期 ==========
@bot.event
async def on_ready():
    bot.add_view(MainView())
    bot.add_view(NextView())
    await bot.tree.sync()
    print(f"✅ Bot起動完了: {bot.user}")


# ✅ スラッシュコマンド
@bot.tree.command(name="panel", description="トークン一括参加パネルを表示")
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔗 トークン一括参加ツール",
        description="⚠️ **重要：絶対に本垢のトークンを使用しないでください。**\n"
                    "✅ 本人確認・参加用とも、全て捨て垢のトークンを使用してください。\n"
                    "✅ このメッセージは**あなただけに表示**され、他の人には見えません。",
        color=0xFFD700
    )
    await interaction.response.send_message(embed=embed, view=MainView(), ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません。")
    bot.run(TOKEN)