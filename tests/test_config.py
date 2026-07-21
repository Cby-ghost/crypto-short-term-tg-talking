from crypto_monitor.config import load_config


def test_config_loads_without_telegram_credentials(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    config = load_config("config.yaml")

    assert config.telegram_bot_token == ""
    assert config.telegram_chat_id == ""
    assert config.timeframe == "15m"
