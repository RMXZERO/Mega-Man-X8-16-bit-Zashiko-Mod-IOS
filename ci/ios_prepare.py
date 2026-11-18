#!/usr/bin/env python3
"""iOS 빌드 전처리 (멱등). 저장소 루트에서 실행.

1) CharacterManager.gd : iOS를 모바일(터치) 플랫폼으로 취급
2) Character_Spawner.gd: 존재하지 않는 TouchControl.gd 경로 수정
3) project.godot       : iOS 내보내기에 필요한 PVRTC / ETC2 임포트 활성화
4) export_presets.cfg  : iOS 프리셋(preset.N) 추가
5) ko-assets/          : 한글판(exe)에서 추출한 한국어 번역/폰트를 저장소에 덮어쓰기 + 번역 목록에 ko 추가
"""
import shutil
import os
import re
import sys

BUNDLE_ID = os.environ.get("BUNDLE_ID", "com.example.mmx8")
TEAM_ID = os.environ.get("TEAM_ID", "AAAAAAAAAA")  # 서명 안 하므로 형식만 맞는 더미


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def patch_character_manager():
    path = "System/CharacterManager.gd"
    src = read(path)
    if "# iOS-PORT" in src:
        print(f"[skip] {path} (이미 패치됨)")
        return
    nl = "\r\n" if "\r\n" in src else "\n"
    pat = re.compile(
        r"func is_Android\(\) -> bool:\s*\n\s*if OS\.get_name\(\) == \"Android\":\s*\n\s*return true\s*\n\s*return false\s*\n"
        r"func touch_controls_enabled\(\) -> bool:\s*\n\s*if is_Android\(\):\s*\n\s*return touch_controls\s*\n\s*return false",
        re.M,
    )
    new = nl.join([
        "# iOS-PORT: iOS도 모바일(터치) 플랫폼으로 취급",
        "func is_Android() -> bool:",
        "\tvar _os = OS.get_name()",
        "\treturn _os == \"Android\" or _os == \"iOS\"",
        "func touch_controls_enabled() -> bool:",
        "\tif OS.get_name() == \"iOS\":",
        "\t\treturn true",
        "\tif is_Android():",
        "\t\treturn touch_controls",
        "\treturn false",
    ])
    out, n = pat.subn(lambda m: new, src, count=1)
    if n != 1:
        sys.exit(f"[error] {path}: is_Android 블록을 찾지 못함 (소스가 바뀌었는지 확인)")
    write(path, out)
    print(f"[ok]   {path}")


def patch_spawner():
    path = "System/Character_Spawner.gd"
    src = read(path)
    old = 'res://Axl_mod/system/Android/TouchControl.gd'
    new = 'res://System/Android/TouchControl.gd'
    if old not in src:
        print(f"[skip] {path} (이미 패치됨/경로 없음)")
        return
    write(path, src.replace(old, new))
    print(f"[ok]   {path}")


def patch_project_godot():
    path = "project.godot"
    src = read(path)
    nl = "\r\n" if "\r\n" in src else "\n"
    m = re.search(r"^\[rendering\]\s*$", src, re.M)
    if not m:
        sys.exit("[error] project.godot에 [rendering] 섹션이 없음")
    want = ["vram_compression/import_pvrtc=true", "vram_compression/import_etc2=true"]
    add = [w for w in want if w.split("=")[0] not in src]
    if not add:
        print("[skip] project.godot (이미 설정됨)")
        return
    ins = m.end()
    src = src[:ins] + nl + nl.join(add) + src[ins:]
    write(path, src)
    print(f"[ok]   project.godot += {add}")


PRESET = """
[preset.{n}]

name="iOS"
platform="iOS"
runnable=true
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter="*.ase, *.aseprite, *.pdn, *.csv, *.txt, *.md, *.zip, *.dll, *.exe, *.ico, *.gif, *.world"
export_path=""
script_export_mode=1
script_encryption_key=""

[preset.{n}.options]

application/app_store_team_id="{team}"
application/identifier="{bundle}"
application/bundle_identifier="{bundle}"
application/short_version="1.0"
application/version="1.0.0"
application/launch_screens_interpolation=0
application/targeted_device_family=2
orientation/portrait=false
orientation/landscape_left=true
orientation/landscape_right=true
"""


def patch_presets():
    path = "export_presets.cfg"
    src = read(path) if os.path.exists(path) else ""
    if re.search(r'^platform="iOS"', src, re.M):
        print("[skip] export_presets.cfg (iOS 프리셋 이미 있음)")
        return
    nums = [int(x) for x in re.findall(r"^\[preset\.(\d+)\]", src, re.M)]
    n = (max(nums) + 1) if nums else 0
    nl = "\r\n" if "\r\n" in src else "\n"
    block = PRESET.format(n=n, team=TEAM_ID, bundle=BUNDLE_ID).replace("\n", nl)
    write(path, src.rstrip() + nl + block)
    print(f"[ok]   export_presets.cfg += preset.{n} (iOS)")


def apply_korean():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ko-assets")
    root = os.path.normpath(root)
    if not os.path.isdir(root):
        print("[skip] ko-assets/ 없음 (한국어 미적용)")
        return
    n = 0
    for base, _, files in os.walk(root):
        for name in files:
            src = os.path.join(base, name)
            rel = os.path.relpath(src, root)
            os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
            shutil.copyfile(src, rel)
            n += 1
    print(f"[ok]   ko-assets: {n}개 파일 복사")
    # project.godot 번역 목록에 ko 추가
    path = "project.godot"
    src = read(path)
    ko = "res://src/Localization/real_translations.ko.translation"
    if ko in src:
        print("[skip] project.godot (ko 번역 이미 등록됨)")
        return
    m = re.search(r"(translations=PoolStringArray\()(.*?)(\s*\))", src, re.S)
    if not m:
        sys.exit("[error] project.godot에서 locale/translations 목록을 찾지 못함")
    body = m.group(2).rstrip()
    new = body + ', "' + ko + '"' if body.strip() else '"' + ko + '"'
    src = src[: m.start(2)] + new + src[m.end(2):]
    write(path, src)
    print("[ok]   project.godot += ko 번역")


if __name__ == "__main__":
    if not os.path.exists("project.godot"):
        sys.exit("[error] 저장소 루트(project.godot가 있는 곳)에서 실행하세요")
    patch_character_manager()
    patch_spawner()
    patch_project_godot()
    patch_presets()
    apply_korean()
