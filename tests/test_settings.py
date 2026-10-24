from app.user_settings import (
    LLM_PRESETS,
    EMBEDDING_PRESETS,
    LLMSettings,
    SettingsStore,
    UserSettings,
    merge_update,
    public_view,
)


def test_store_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "s" / "settings.json")
    assert store.load() == UserSettings()
    s = UserSettings(llm=LLMSettings(api_key="sk-secret-123456"))
    store.save(s)
    assert store.load().llm.api_key == "sk-secret-123456"


def test_public_view_hides_keys():
    view = public_view(UserSettings(llm=LLMSettings(api_key="sk-ant-abcdefgh1234")))
    assert "api_key" not in view["llm"]
    assert view["llm"]["has_api_key"] is True
    assert view["llm"]["api_key_hint"].endswith("1234")
    assert view["embedding"]["has_api_key"] is False


def test_empty_key_keeps_existing_only_for_same_preset():
    current = UserSettings(llm=LLMSettings(preset="claude", api_key="claude-key"))
    same = merge_update(current, UserSettings(llm=LLMSettings(preset="claude", model="claude-sonnet-5-5")))
    assert same.llm.api_key == "claude-key" and same.llm.model == "claude-sonnet-5-5"
    switched = merge_update(current, UserSettings(llm=LLMSettings(preset="deepseek", provider="openai_compatible")))
    assert switched.llm.api_key == ""


def test_presets_are_consistent():
    for p in LLM_PRESETS.values():
        assert p["provider"] in ("anthropic", "openai_compatible")
    for p in EMBEDDING_PRESETS.values():
        assert p["provider"] in ("api", "local")
