// ==========================================
// 🚀 pm2 起動定義（makeitaquote-bot-py）
// ==========================================
// 起動: pm2 start ecosystem.config.cjs
// 再起動後も常駐させるには pm2 startup（表示されたコマンドを実行）と
// pm2 save を行う。
//
// .env は Bot 本体（makeitaquote/config.py）が自分で読み込むため、
// このファイルでは環境変数の受け渡しはしない。秘密情報は .env
// （gitignore 済み）にだけ置き、このファイルには書かない。
// READY ウォッチドッグ（makeitaquote/watchdog.py）が停滞を検知して
// プロセスを終了させた場合も、pm2 の autorestart で再起動する前提の構成。

module.exports = {
  apps: [
    {
      name: "makeitaquote-bot-py",
      script: "./run.sh",
      interpreter: "bash",
      cwd: __dirname,
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "200M",
      kill_timeout: 5000,
    },
  ],
};
