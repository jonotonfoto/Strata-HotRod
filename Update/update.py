#!/usr/bin/env python3
"""update.py — обновлятор установки Strata-HotRod из форка.

Что делает:
  1. Обновляет КОД и документы: serve/, src/, include/, tools/, docs/, Update/.
  2. Если движок в engine/ собран из этого кода (engine/BUILD.json: "source": "local") и код движка с тех пор
     изменился — пересобирает движок тем же шагом, что и установка (setup.py). Компилируются только изменённые
     файлы. Работающий движок заменить нельзя: тогда updater просит закрыть сервер и запустить его ещё раз.

Не трогает: модели, конфиги *.json, .bat, .venv, логи, папку backups/.
Перед заменой каждого файла делает копию в backups/update-<метка>/ .

Запуск:  python Update/update.py            (или двойным кликом update.bat)
Флаги:   --dry-run    только показать, что изменится (ничего не пишет и не собирает)
         --download   качать архив, даже если установка под git
         --ref NAME   ветка или хэш в форке (по умолчанию main)
         --no-engine  не пересобирать движок, только код

Код форка: https://github.com/jonotonfoto/Strata-HotRod
"""
import argparse
import io
import json
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

FORK = "https://github.com/jonotonfoto/Strata-HotRod"
FORK_REPO = "jonotonfoto/Strata-HotRod"
CODE_DIRS = ("serve", "src", "include", "tools", "docs", "Update")
ENGINE_DIRS = ("src", "include")
SKIP_PARTS = ("__pycache__", ".git")
# update.bat запускает этот скрипт: cmd читает .bat по ходу выполнения, заменять его из-под него нельзя
SKIP_FILES = ("Update/update.bat",)
MARKER = "an elastic encoder sleeps between pictures"  # строка-признак фикса зрения


def say(msg=""):
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
    if rel.as_posix() in SKIP_FILES:
        return False
    return len(parts) > 1 and parts[0] in CODE_DIRS


def run_git(root: Path, args, check=True):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        say("ОШИБКА git: " + (r.stderr or r.stdout).strip()[:400])
        sys.exit(1)
    return r


def fork_remote(root: Path) -> str:
    """Имя git-remote, который указывает на форк: обычно origin, но клон мог быть сделан с другого адреса."""
    out = run_git(root, ["remote", "-v"], check=False).stdout
    names = [line.split()[0] for line in out.splitlines()
             if len(line.split()) >= 2 and FORK_REPO.lower() in line.split()[1].lower()]
    return names[0] if names else "origin"


def git_pull(root: Path, dry: bool) -> bool:
    """Обновление через git. True — если что-то изменилось."""
    remote = fork_remote(root)
    run_git(root, ["fetch", remote])
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
    if dry:
        target = run_git(root, ["rev-parse", f"{remote}/main"]).stdout.strip()
        say(f"git ({remote}): {before[:8]} -> {target[:8]}" + (" (уже там)" if before == target else " (обновит)"))
        return False
    run_git(root, ["merge", "--ff-only", f"{remote}/main"])
    after = run_git(root, ["rev-parse", "HEAD"]).stdout.strip()
    say(f"git ({remote}): {before[:8]} -> {after[:8]}")
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
            if old == new or (old is not None and old.replace(b"\r\n", b"\n") == new.replace(b"\r\n", b"\n")):
                continue                                # тот же файл (или только с другими концами строк)
            cpp_changed += 1 if rel.parts[0] in ENGINE_DIRS else 0
            if dry:
                say(f"  изменит: {rel.as_posix()}")
            else:
                if old is not None:
                    bpath = backup_dir / rel
                    bpath.parent.mkdir(parents=True, exist_ok=True)
                    bpath.write_bytes(old)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(new)
                say(f"  обновил: {rel.as_posix()}")
            changed += 1
    if changed and not dry:
        say(f"Копии заменённых файлов: {backup_dir}")
    if cpp_changed:
        say(f"Изменены файлы кода движка: {cpp_changed}.")
    return changed > 0


def venv_python(root: Path) -> str:
    for p in (root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


def engine_is_stale(root: Path) -> bool:
    """Собран ли движок из более старого кода, чем лежит в папке: тот же отпечаток, что считает setup.py."""
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import setup; "
            "m = json.loads(open(sys.argv[2], encoding='utf-8').read()); "
            "print('STALE' if m.get('src') != setup.source_hash(setup.ENGINE_SOURCES) else 'FRESH')")
    r = subprocess.run([venv_python(root), "-c", code, str(root), str(root / "engine" / "BUILD.json")],
                       cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    last = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or last not in ("STALE", "FRESH"):
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:] or "setup.py не ответил")
    return last == "STALE"


def engine_in_use(root: Path) -> bool:
    """Windows держит файл работающего движка закрытым для записи; на Linux проверка всегда проходит."""
    for name in ("strata.exe", "strata-vision.exe", "strata", "strata-vision"):
        p = root / "engine" / name
        if p.exists():
            try:
                with open(p, "r+b"):
                    pass
            except OSError:
                return True
    return False


def engine_step(root: Path, dry: bool) -> str:
    """Пересборка движка, если он собран здесь и его код изменился. Возвращает, чем кончилось:
    none / prebuilt / fresh / would / busy / rebuilt / failed."""
    build = root / "engine" / "BUILD.json"
    if not build.exists():
        say("Движок: в engine/ его ещё нет (установка не закончена) — собирать нечего.")
        return "none"
    try:
        meta = json.loads(build.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    if meta.get("source") != "local":
        say("Движок: готовый, не собранный из этого кода. Правок форка в нём нет, и updater его не меняет.")
        say("  Как собрать движок из кода форка: docs/SPEED_FIXES_SETUP.md, раздел 2 (установка с --build).")
        return "prebuilt"
    try:
        stale = engine_is_stale(root)
    except Exception as e:
        say(f"Движок: не удалось сверить его с кодом ({e}). Движок оставлен как есть.")
        return "failed"
    if not stale:
        say("Движок: собран из текущего кода, пересборка не нужна.")
        return "fresh"
    if dry:
        say("Движок: собран из более старого кода — обновление пересоберёт его (изменённые файлы, несколько минут).")
        return "would"
    if engine_in_use(root):
        say("Движок: код обновлён, но движок сейчас РАБОТАЕТ, заменить его нельзя.")
        say("  Закрой сервер и запусти update ещё раз — тогда движок пересоберётся.")
        say("  До этого сервер работает на прежнем движке: новые переключатели он не знает и пропускает.")
        return "busy"
    say("Движок: пересобираю из обновлённого кода (изменённые файлы; обычно несколько минут) ...")
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import setup; "
            "setup.update_installed_engine(setup.PREBUILT_URL)")
    subprocess.run([venv_python(root), "-c", code, str(root)], cwd=root)
    try:
        stale = engine_is_stale(root)
    except Exception:
        stale = True
    if stale:
        say("Движок: пересборка НЕ удалась (причина выше). Прежний движок на месте и работает как раньше.")
        say("  Что нужно для сборки: docs/SPEED_FIXES_SETUP.md, раздел 2. Потом запусти update ещё раз.")
        return "failed"
    say("Движок: пересобран.")
    return "rebuilt"


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
    ap.add_argument("--no-engine", action="store_true")
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
        say("Код: проверка без записи закончена." if a.dry_run else "Код: уже самый свежий — менять нечего.")
    verify(root)
    engine = "skipped" if a.no_engine else engine_step(root, a.dry_run)
    say()
    if a.dry_run:
        say("Это была проверка (--dry-run): ничего не записано и не собрано.")
        return
    if engine == "busy":
        say("Осталось: закрыть сервер и запустить update ещё раз (пересборка движка).")
    elif engine == "failed":
        say("Код обновлён, движок прежний. Сервер можно запускать: он работает как до обновления.")
    elif changed or engine == "rebuilt":
        say("Готово. Перезапусти сервер HotRod (его батник запуска), чтобы обновление заработало:")
        say("сам updater сервер не перезапускает, чтобы не рвать твою текущую работу.")
        say("Что нового и что включить в конфиге: Update/CHANGELOG.md.")


if __name__ == "__main__":
    main()
