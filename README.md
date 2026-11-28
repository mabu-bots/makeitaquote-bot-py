# 💬 Make It a Quote Bot（makeitaquote-bot-py）

Discord のメッセージや任意のテキストから、**名言風の画像**を生成する Bot です。
TypeScript 版（makeitaquote-bot）の Python 移植で、機能と出力は同一です。
左側にグレースケール化したアバター写真（右へ向けて黒にフェード）、右側に
M PLUS Rounded 1c の引用文を中央寄せで配置する、本家「Make It a Quote」の
出力に寄せた形式の画像を作ります。

| 項目 | 内容 |
|---|---|
| バージョン | 1.0.0 |
| 状態 | 稼働中（Python 版） |
| 稼働先 | 台3 minase（pm2: makeitaquote-bot-py） |
| 実装 | Python（discord.py 2.4+、Pillow） |
| 更新履歴 | [CHANGELOG.md](CHANGELOG.md) |

## 📖 概要

言っていないことを言ったことにする、お遊び用の捏造画像ジェネレータです。

![サンプル](docs/sample.png)

## ✨ 機能

- 生成した画像には「🗑️ 削除する」ボタンが付きます。押せるのは
  **引用された本人（ユーザーIDを使用された人）と、画像を作成した人だけ**です。
  それ以外の人が押しても削除されず、その旨が本人にだけ見える形で返ります。
  言っていないことを言ったことにされた側が、自分で画像を取り消せるための仕組みです。

## 📝 コマンド

| コマンド | 権限 | 内容 |
|---|---|---|
| メッセージの右クリック → アプリ →「Make it a Quote」 | 全員 | 実際の発言を、そのまま名言画像にします。発言者のアバターと表示名が入ります |
| `/quote user:<ユーザー> text:<テキスト>` | 全員 | 指定したユーザーが言ったことにして、任意のテキストで名言画像を捏造します（テキストは最大 300 文字） |

## 👀 プレゼンス

- Playing で、1分ごとに次の2パターンを交互に表示します（全 Bot 共通のサイクル仕様）。
  - `<Bot名> | 起動して <経過時間>`（起点はログイン完了時、分粒度）
  - `<Bot名> | 現在時刻 HH:MM JST`
- 位相は Unix 分の偶奇で決まるため全 Bot が同時に切り替わり、値は分の境界
  時点のものを境界の 200ms 前に先行送信します。

## 🚀 セットアップ

1. [Discord 開発者ポータル](https://discord.com/developers/applications) で
   アプリケーションを作成し、Bot を追加します。**特権インテントは不要**です。
2. Bot をサーバーへ招待します。スコープは `bot` と `applications.commands`、
   権限は「メッセージを送信」と「ファイルを添付」があれば十分です。
3. `.env.example` を `.env` にコピーし、`DISCORD_TOKEN` と `CLIENT_ID` を
   設定します。開発中は `GUILD_ID` を設定するとコマンド登録が即時反映されます。
4. 起動します。コマンドは起動時に自動登録されます。

| 変数 | 必須 | 内容 |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot のトークン |
| `CLIENT_ID` | ✅ | アプリケーションのクライアント ID |
| `GUILD_ID` | – | 設定すると、そのサーバーにだけコマンドを即時登録（開発用） |
| `QUOTE_ARCHIVE` | – | `off` で生成画像のアーカイブ保存を止める（「運用」参照） |
| `QUOTE_ARCHIVE_DIR` | – | アーカイブの保存先を変更する |

```bash
pip install -r requirements.txt
./run.sh        # または python -m makeitaquote
```

## 🔄 運用

pm2 での常駐:

```bash
pm2 start ecosystem.config.cjs
pm2 startup   # 表示されたコマンドを実行
pm2 save
```

生成物アーカイブ:

- 生成した画像は不適切な使用がないか確認できるよう、Bot のサーバー内
  （`data/archive/`）に自動保存されます。`index.jsonl` に日時・作成者・
  引用された人・本文が記録され、保持は最大30日／最大1000件（古い順に自動削除）。
- この保存先は運営者だけが見られます。止める場合は環境変数 `QUOTE_ARCHIVE=off`。

## 🧪 テスト

```bash
./build.sh      # 依存解決 + 単体テスト（折り返し・禁則・レンダラ・Bot 本体）
```

テストは 85 件（v1.0.0 時点）。

サンプル画像の再生成は `python -m makeitaquote.sample` です。

## 📁 ファイル構成

| パス | 役割 |
|---|---|
| `makeitaquote/` | 本体パッケージ（Bot、描画、アーカイブ、ウォッチドッグ） |
| `tests/` | 単体テスト（pytest） |
| `assets/fonts/` | 同梱フォント（M PLUS Rounded 1c / Noto Sans JP） |
| `docs/` | サンプル画像 |
| `data/` | 生成物アーカイブの保存先（実行時に生成） |
| `run.sh` | 起動スクリプト |
| `ecosystem.config.cjs` | pm2 の起動定義 |
| `build.sh` / `build.bat` | ワンコマンドビルド（テスト込み） |

## 📋 仕様メモ

- 描画は Pillow、フォントは `assets/fonts/` の M PLUS Rounded 1c（引用文・発言者名）
  と Noto Sans JP（クレジット）を同梱して使うため、実行環境のフォントに
  依存しません（いずれも SIL Open Font License）。
- 引用文は日本語の禁則処理（行頭・行末禁則）付きで折り返し、収まる最大の
  フォントサイズを自動で選びます。
- アバターの取得に失敗した場合は、名前から決まる色のグラデーションと
  頭文字の代替画像を使います。
- 画像生成はイベントループを塞がないよう、別スレッドで実行します。

## ⚠️ 注意

捏造画像は、内輪の冗談として楽しむ範囲で使ってください。本人が言っていない
発言を本物らしく見せて第三者を欺く用途には使わないでください。

## 🔗 関連

- TypeScript 版（本番）: [makeitaquote-bot](https://github.com/mabu-bots/makeitaquote-bot)
