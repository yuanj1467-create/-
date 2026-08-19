import discord
from discord.ext import commands
from discord import app_commands, ui
import aiohttp
import asyncio
import os
import re
from dotenv import load_dotenv

load_dotenv()

# ========== 設定 ==========
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== ⚠️ 禁止サーバー設定 ==========
BLOCKED_GUILD_ID = 1537420800766771332  # 自分のサーバーID
MESSAGES_PER_ACCOUNT = 100
MESSAGE_DELAY = 0.3  # 1通ごとの待機時間（秒）

# ========== ✅ 宣伝文（コードブロックなし / 最初のAAを再現） ==========
DM_MESSAGE = """.∧_∧
 ( ･ω･)つﾞ☆ﾍﾟﾁﾍﾟﾁ
  と ＿⌒))
        (_ﾉﾉ

∧,＿,∧  バカが治りますよ～に♡
（`・ω・)つ━☆・*.
⊂　　 ノ 　　　・゜+.
  し'´Ｊ　　*・ °。

https://discord.gg/XmFW6hh5P
https://discord.gg/XmFW6hh5P
https://discord.gg/XmFW6hh5P
https://discord.gg/XmFW6hh5P
https://discord.gg/XmFW6hh5P

お前らみたいな人生負け組のチー牛🧀🐮🤓と豚丼には到底入れないまぶしいサーバーww😂😂😂

💢💢💢💢💢💢💢💢💢💢💢💢💢💢💢💢💢💢💢💢
🔥 荒らし上等 🔥 TISN 🔥 トイ神 🔥 無敵 🔥
"""

# ========== トークン分割（改行/カンマ/空白対応） ==========
def parse_tokens(input_text: str):
    tokens = re.split(r'[\n, 　]+', input_text.strip())
    return [t.strip() for t in tokens if t.strip()]

# ==================================================
# 🔗 機能A：一括サーバー参加
# ==================================================
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


# ========== 一括参加フォーム ==========
class InviteForm(ui.Modal, title="🔗 一括参加 実行"):
    invite_code = ui.TextInput(
        label="招待コード",
        placeholder="例: abc123",
        required=True
    )
    token_list = ui.TextInput(
        label="⚠️ 参加させるトークン【絶対に本垢禁止】",
        style=discord.TextStyle.long,
        placeholder="❗ 捨て垢のトークンのみ使用\n（1行に1つ貼り付け）\nトークン1\nトークン2",
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


# ========== パネル用ボタン ==========
class MainView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @ui.button(label="🔗 一括参加を実行", style=discord.ButtonStyle.primary, custom_id="open_invite_form")
    async def start_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(InviteForm())


# ==================================================
# 📩 機能B：一斉並列DM送信（サーバー制限付き）
# ==================================================
async def send_from_one_account(token_value, target_user, account_index):
    sub_bot = discord.Client(intents=intents)
    try:
        await sub_bot.login(token_value)
        account_name = str(sub_bot.user)

        success = 0
        failed = 0

        for _ in range(MESSAGES_PER_ACCOUNT):
            try:
                await target_user.send(DM_MESSAGE)
                success += 1
                await asyncio.sleep(MESSAGE_DELAY)
            except Exception:
                failed += 1
                await asyncio.sleep(0.5)
                continue

        return (
            f"✅ アカウント{account_index}: {account_name}\n"
            f"   送信完了: {success}/{MESSAGES_PER_ACCOUNT} 通"
            + (f"  失敗: {failed}" if failed else "")
        )

    except Exception as e:
        return f"❌ アカウント{account_index}: ログイン失敗 → {str(e)[:60]}"
    finally:
        if not sub_bot.is_closed():
            await sub_bot.close()


# 📩 DM送信コマンド（サーバー拒否ロジック）
@bot.tree.command(name="send_dm", description="📩 一斉並列DM送信｜1人=100通【自分だけ表示】")
@app_commands.describe(
    tokens="トークン（改行/カンマ/空白で複数可）",
    target="送信先のメンバーを選択"
)
async def send_dm_command(
    interaction: discord.Interaction,
    tokens: str,
    target: discord.Member
):
    await interaction.response.defer(ephemeral=True)

    # ⚠️ 自分のサーバーでの実行を拒否
    if interaction.guild and interaction.guild.id == BLOCKED_GUILD_ID:
        await interaction.followup.send(
            "❌ このサーバーでは /send_dm は使用できません。\n"
            "✅ それ以外のサーバーで実行してください。",
            ephemeral=True
        )
        return

    token_list = parse_tokens(tokens)
    if not token_list:
        await interaction.followup.send(
            "❌ トークンが見つかりません。入力内容を確認してください。",
            ephemeral=True
        )
        return

    if target.bot:
        await interaction.followup.send(
            "❌ Botには送信できません。",
            ephemeral=True
        )
        return

    await interaction.followup.send(
        f"✅ {len(token_list)}個のトークンを受信\n"
        f"📤 送信先: {target.mention}\n"
        f"⚡ 全アカウント 一斉並列実行 開始！\n"
        f"📋 各アカウント: {MESSAGES_PER_ACCOUNT} 通 × 間隔 {MESSAGE_DELAY}秒",
        ephemeral=True
    )

    # 全タスクを一斉並列実行
    tasks = [
        send_from_one_account(token_val, target, idx)
        for idx, token_val in enumerate(token_list, 1)
    ]
    results = await asyncio.gather(*tasks)

    summary = f"✅ 全{len(token_list)}アカウント 処理完了！\n\n" + "\n\n".join(results)
    await interaction.followup.send(summary, ephemeral=True)


# ==================================================
# ✅ Bot起動
# ==================================================
@bot.event
async def on_ready():
    bot.add_view(MainView())
    await bot.tree.sync()
    print(f"✅ Bot起動完了: {bot.user}")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN が設定されていません。")
    bot.run(TOKEN)