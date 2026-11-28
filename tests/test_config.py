# ⚙️ 設定ローダーのテスト
import pytest

from makeitaquote.config import _strip_value, load_config


# ------------------------------------------
# 値の整形（インラインコメントと引用符）
# ------------------------------------------
def test_inline_comment_removed():
    assert _strip_value("abc123 # トークン") == "abc123"


def test_inline_comment_removed_from_int_value():
    assert _strip_value("123456 # クライアントID") == "123456"


def test_hash_without_preceding_space_is_kept():
    assert _strip_value("abc#123") == "abc#123"


def test_hash_inside_quotes_is_kept():
    assert _strip_value('"ab # cd"') == "ab # cd"


def test_comment_after_quoted_value_removed():
    assert _strip_value('"abc" # コメント') == "abc"


def test_surrounding_quotes_removed():
    assert _strip_value("'token'") == "token"


# ------------------------------------------
# load_config
# ------------------------------------------
@pytest.fixture()
def clean_env(monkeypatch, tmp_path):
    """トークン類を消し、.env の無いディレクトリへ移動する。"""
    for name in ("DISCORD_TOKEN", "CLIENT_ID", "GUILD_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def test_missing_token_raises(clean_env):
    clean_env.setenv("CLIENT_ID", "123")
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        load_config()


def test_missing_client_id_raises(clean_env):
    clean_env.setenv("DISCORD_TOKEN", "tok")
    with pytest.raises(RuntimeError, match="CLIENT_ID"):
        load_config()


def test_invalid_client_id_error_names_variable(clean_env):
    clean_env.setenv("DISCORD_TOKEN", "tok")
    clean_env.setenv("CLIENT_ID", "abc")
    with pytest.raises(RuntimeError, match="CLIENT_ID"):
        load_config()


def test_invalid_guild_id_error_names_variable(clean_env):
    clean_env.setenv("DISCORD_TOKEN", "tok")
    clean_env.setenv("CLIENT_ID", "123")
    clean_env.setenv("GUILD_ID", "xyz")
    with pytest.raises(RuntimeError, match="GUILD_ID"):
        load_config()


def test_valid_ids_parse(clean_env):
    clean_env.setenv("DISCORD_TOKEN", "tok")
    clean_env.setenv("CLIENT_ID", "123456")
    clean_env.setenv("GUILD_ID", "789")
    config = load_config()
    assert config.token == "tok"
    assert config.client_id == 123456
    assert config.guild_id == 789


def test_guild_id_is_optional(clean_env):
    clean_env.setenv("DISCORD_TOKEN", "tok")
    clean_env.setenv("CLIENT_ID", "42")
    assert load_config().guild_id is None


def test_dotenv_file_is_loaded(clean_env, tmp_path):
    (tmp_path / ".env").write_text(
        "DISCORD_TOKEN=file-token # コメント\nCLIENT_ID=555\n", encoding="utf-8"
    )
    config = load_config()
    assert config.token == "file-token"
    assert config.client_id == 555
