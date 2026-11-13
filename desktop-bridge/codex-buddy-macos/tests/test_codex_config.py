import shlex

from src.codex_config import install_codex_hooks


def test_install_quotes_hook_command_with_spaces(tmp_path):
    hooks_path = tmp_path / "hooks.json"
    bin_path = "/Applications/PixelMug Codex.app/Contents/MacOS/PixelMug Codex"

    install_codex_hooks(bin_path, path=hooks_path)

    command = hooks_path.read_text(encoding="utf-8")
    assert f"{shlex.quote(bin_path)} hook" in command
