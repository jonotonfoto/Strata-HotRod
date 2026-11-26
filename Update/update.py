#!/usr/bin/env python3
"""update.py — обновлятор установки Strata-HotRod из форка.

Обновляет только КОД (serve/, src/, include/, tools/).
Не трогает: модели, конфиги *.json, .bat, .venv, engine/, логи, папку backups/.
Перед заменой каждого файла делает копию в backups/update-<метка>/ .

Запуск:  python Update/update.py            (или двойным кликом update.bat)
Флаги:   --dry-run   только показать, что меняется
         --download  качать архив, даже если установка под git
         --ref NAME  ветка или хэш в форке (по умолчанию main)

Код форка: https://github.com/jonotonfoto/Strata-HotRod
"""
import argparse
import io
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

FORK = "https://github.com/jonotonfoto/Strata-HotRod"
CODE_DIRS = ("serve", "src", "include", "tools")
SKIP_PARTS = ("__pycache__", ".git")
MARKER = "an elastic encoder sleeps between pictures"  # строка-признак фикса зрения


def say(msg):
    print(msg, flush=True)


def install_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not (root / "serve" / "server.py").exists():
        say(f"ОШИБКА: это не похоже на установку HotRod: {root}")
        say("Папка Update должна лежать в корне распакованного форка.")
        sys.exit(2)
    return root


def is_code(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_PARTS for p in parts):
        return False
    return len(parts) > 1 and parts[0] in CODE_DIRS


def run_git(root: Path, args, check=True):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        say("ОШИБКА git: " + (r.stderr or r.stdout).strip()[:400])
        sys.exit(1)
    return r


def git_pull(root: Path, dry: bool) -> bool:
    """Обновление через git. True — если что-то изменилось."""
    run_git(root, ["fetch", "origin"])
    dirty = run_git(root, ["status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if dirty:
        say("В установке есть твои несохранённые правки файлов:")
        for line in dirty.splitlines()[:10]:
            say("  " + line)
        say("Git-обновление с ними не работает, чтобы не потерять твоё.")
        say("Скажи агенту: пусть обновит через Update/update.py --download —")
        say("он сохранит копии спорных файлов и обновит код с их заменой.")
        sys.exit(3)
    before = run_git(root, ["rev-parse", "HEAD"]).stdout.strip()
    if not dry:
        run_git(root, ["merge", "--ff-only", "origin/main"])
    after = run_git(root, ["rev-parse", "HEAD"]).stdout.strip()
    say(f"git: {before[:8]} -> {after[:8]}")
    return before != after


def download_update(root: Path, ref: str, dry: bool) -> bool:
    """Обновление кода из zip-архива форка. True — если заменён хотя бы 1 файл."""
    url = f"{FORK}/archive/{ref}.zip"
    say(f"Скачиваю архив: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "hotrod-update"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    say(f"Архив: {len(data) // (1024 * 1024)} МиБ")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = root / "backups" / f"update-{stamp}"
    changed, cpp_changed = 0, 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            say("ОШИБКА: архив пустой.")
            sys.exit(1)
        prefix = names[0].split("/", 1)[0] + "/"
        for name in names:
            rel = Path(name[len(prefix):])
            if not is_code(rel):
                continue
            target = root / rel
            new = z.read(name)
            old = target.read_bytes() if target.exists() else None
            if old == new:
                continue
            cpp_changed += 1 if rel.parts[0] in ("src", "include") else 0
            if dry:
                say(f"  изменит: {rel}")
            else:
                if old is not None:
                    bpath = backup_dir / rel
                    bpath.parent.mkdir(parents=True, exist_ok=True)
                    bpath.write_bytes(old)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(new)
                say(f"  обновил: {rel}")
            changed += 1
    if changed and not dry:
        say(f"Копии заменённых файлов: {backup_dir}")
    if cpp_changed:
        say("ВНИМАНИЕ: изменены C-файлы движка. Чтобы новый код движка заработал,"
            " нужна пересборка (build_engine). Спроси агента — он объяснит.")
    return changed > 0


def verify(root: Path):
    import py_compile
    try:
        py_compile.compile(str(root / "serve" / "server.py"), doraise=True)
    except Exception as e:
        say(f"ОШИБКА: server.py после обновления не проверяется: {e}")
        say("Файлы заменены; копии — в backups\\update-*. Сервер не перезапускай.")
        sys.exit(4)
    body = (root / "serve" / "server.py").read_text(encoding="utf-8", errors="replace")
    say("server.py синтаксически цел, проверка пройдена.")
    if MARKER in body:
        say("Фикс картинок из инструментов — установлен.")
    else:
        say("Фикс картинок из инструментов — НЕ найден (форк ещё не обновлён?)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--ref", default="refs/heads/main")
    a = ap.parse_args()
    root = install_root()
    say(f"Установка: {root}")
    changed = False
    if (root / ".git").exists() and not a.download:
        say("Способ: git")
        changed = git_pull(root, a.dry_run)
    else:
        say("Способ: скачивание архива" + (" (по флагу --download)" if a.download else ""))
        changed = download_update(root, a.ref, a.dry_run)
    if not changed:
        say("Уже самое свежее — менять нечего.")
    verify(root)
    if changed and not a.dry_run:
        say("")
        say("Готово. Перезапусти сервер HotRod (его батник запуска),")
        say("чтобы фикс заработал: перезапуск сам updater не делал,")
        say("чтобы не рвать твою текущую работу.")


if __name__ == "__main__":
    main()
