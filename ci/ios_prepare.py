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
        "# iOS-PORT: iOS도 모바일(터치) 플랫폼으로 취급 (스테이지 터치 UI는 IOSTouchOverlay 가 담당)",
        "func is_Android() -> bool:",
        "\tvar _os = OS.get_name()",
        "\treturn _os == \"Android\" or _os == \"iOS\"",
        "func touch_controls_enabled() -> bool:",
        "\tif OS.get_name() == \"iOS\":",
        "\t\treturn false",
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
icons/app_store_1024x1024="res://ci_icon_1024.png"
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


OVERLAY_GD = r'''extends CanvasLayer
# iOS 가상 패드 (UnleashedRecompiled 의 XeniOS 스타일 레이아웃을 Godot 으로 옮김)
# - 왼쪽: 스틱 + D-패드 링 / 오른쪽: A B X Y / 위: LB RB BACK START / 양옆: LT RT
# - 캐릭터를 고른 뒤 스테이지(플레이어가 있을 때)에서만 표시, 메뉴에서는 화면을 직접 터치
# - 블루투스 컨트롤러가 연결되어 있으면 자동으로 숨김

const STICK_DEADZONE = 0.14
const STICK_ACTIVATION_RADIUS = 0.48
const STICK_DPAD_RING_RADIUS = 0.32
const WIDE_SCREEN_SAFE_MARGIN = 0.055
const DIGITAL_THRESHOLD = 0.35

var stick_frame = Rect2(0.055, 0.560, 0.190, 0.315)

# [id, 표시 글자, 프레임(0~1), 연결할 게임 액션]
var buttons = [
	["back", "BACK", Rect2(0.390, 0.045, 0.080, 0.112), ["select"]],
	["start", "START", Rect2(0.495, 0.045, 0.085, 0.112), ["pause"]],
	["lb", "LB", Rect2(0.095, 0.268, 0.120, 0.112), ["weapon_select_left"]],
	["rb", "RB", Rect2(0.860, 0.268, 0.120, 0.112), ["weapon_select_right"]],
	["lt", "LT", Rect2(0.095, 0.405, 0.120, 0.110), ["reset_weapon"]],
	["rt", "RT", Rect2(0.860, 0.405, 0.120, 0.110), ["select_special"]],
	["y", "Y", Rect2(0.760, 0.455, 0.065, 0.115), ["alt_fire"]],
	["x", "X", Rect2(0.700, 0.585, 0.065, 0.115), ["fire", "ui_accept"]],
	["b", "B", Rect2(0.820, 0.585, 0.065, 0.115), ["dash", "ui_cancel"]],
	["a", "A", Rect2(0.760, 0.715, 0.065, 0.115), ["jump", "ui_accept"]],
]

var dir_actions = {
	"left": ["ui_left", "move_left"],
	"right": ["ui_right", "move_right"],
	"up": ["ui_up", "move_up"],
	"down": ["ui_down", "move_down"],
}

var canvas: Control
var font: Font
var captures: Dictionary = {}
var active: Dictionary = {}
var shown: bool = false
var timer: float = 0.0
var tap_index: int = -1
var tap_button = null
var tap_fired: bool = false


func _ready() -> void:
	layer = 100
	pause_mode = Node.PAUSE_MODE_PROCESS
	canvas = Control.new()
	canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(canvas)
	canvas.set_anchors_and_margins_preset(Control.PRESET_WIDE)
	canvas.connect("draw", self, "_on_draw")
	font = canvas.get_font("font", "Label")
	Input.connect("joy_connection_changed", self, "_on_joy_changed")
	set_shown(false)
	timer = 0.0


func _on_joy_changed(_device: int, _connected: bool) -> void:
	timer = 0.0


func _in_stage() -> bool:
	var gm = get_node_or_null("/root/GameManager")
	if gm != null and gm.has_method("is_player_in_scene"):
		return gm.is_player_in_scene()
	return false


func _process(delta: float) -> void:
	timer -= delta
	if timer > 0.0:
		return
	timer = 0.15
	var want_show = OS.get_name() == "iOS" and Input.get_connected_joypads().size() == 0 and _in_stage()
	if want_show != shown:
		set_shown(want_show)


func set_shown(v: bool) -> void:
	shown = v
	canvas.visible = v
	if not v:
		captures.clear()
		_apply()


func _space() -> Rect2:
	var s = get_viewport().get_visible_rect().size
	var margin = 0.0
	if (s.x / s.y) > 1.9:
		margin = s.x * WIDE_SCREEN_SAFE_MARGIN
	return Rect2(margin, 0.0, s.x - margin * 2.0, s.y)


func _to_window(frame: Rect2) -> Rect2:
	var sp = _space()
	return Rect2(sp.position.x + frame.position.x * sp.size.x, sp.position.y + frame.position.y * sp.size.y, frame.size.x * sp.size.x, frame.size.y * sp.size.y)


func _pill_contains(r: Rect2, p: Vector2, grow: float) -> bool:
	var radius = min(r.size.x, r.size.y) * 0.5
	var c = r.position + r.size * 0.5
	var hx = max(r.size.x * 0.5 - radius, 0.0)
	var hy = max(r.size.y * 0.5 - radius, 0.0)
	var dx = max(abs(p.x - c.x) - hx, 0.0)
	var dy = max(abs(p.y - c.y) - hy, 0.0)
	var rr = radius * grow
	return dx * dx + dy * dy <= rr * rr


func _find_control(p: Vector2) -> String:
	if _to_window(stick_frame).has_point(p):
		return "stick"
	for b in buttons:
		if _pill_contains(_to_window(b[2]), p, 1.15):
			return b[0]
	return ""


func _stick_zone(sf: Rect2, p: Vector2) -> String:
	var c = sf.position + sf.size * 0.5
	var ring = min(sf.size.x, sf.size.y) * STICK_DPAD_RING_RADIUS
	var d = p - c
	if d.length() <= ring:
		return "stick"
	if abs(d.x) > abs(d.y):
		if d.x > 0.0:
			return "right"
		return "left"
	if d.y > 0.0:
		return "down"
	return "up"


func _stick_delta(sf: Rect2, cap: Dictionary) -> Vector2:
	var outer = min(sf.size.x, sf.size.y) * STICK_ACTIVATION_RADIUS
	var delta = cap["current"] - cap["anchor"]
	if delta.length() > outer:
		delta = delta.normalized() * outer
	return delta


func _stick_vector(sf: Rect2, cap: Dictionary) -> Vector2:
	var outer = min(sf.size.x, sf.size.y) * STICK_ACTIVATION_RADIUS
	var n = _stick_delta(sf, cap) / outer
	var mag = n.length()
	if mag < STICK_DEADZONE or mag <= 0.0:
		return Vector2.ZERO
	var rescaled = clamp((mag - STICK_DEADZONE) / (1.0 - STICK_DEADZONE), 0.0, 1.0)
	return n / mag * rescaled


func _input(event: InputEvent) -> void:
	if OS.get_name() != "iOS":
		return
	if event is InputEventScreenTouch:
		if event.pressed:
			var p = event.position
			var id = ""
			if shown:
				id = _find_control(p)
			if id == "":
				_begin_tap(event.index, p)
				return
			var cap = {"control": id, "zone": "", "anchor": p, "current": p}
			if id == "stick":
				cap["zone"] = _stick_zone(_to_window(stick_frame), p)
			captures[event.index] = cap
		else:
			if event.index == tap_index:
				_end_tap(event.position)
			captures.erase(event.index)
		_apply()
	elif event is InputEventScreenDrag:
		if captures.has(event.index):
			captures[event.index]["current"] = event.position
			_apply()


# 메뉴의 화살표 같은 X8 버튼을 직접 눌렀을 때: 기본 마우스 에뮬레이션으로 눌리지 않으면 대신 눌러 줌
func _find_button_at(node: Node, p: Vector2):
	if node == self:
		return null
	var kids = node.get_children()
	for i in range(kids.size() - 1, -1, -1):
		var found = _find_button_at(kids[i], p)
		if found != null:
			return found
	if node is TextureButton and node.has_method("on_press") and not node.disabled and node.focus_mode != Control.FOCUS_NONE:
		if node.is_visible_in_tree() or _hidden_hit_area_ok(node):
			if _button_has_point(node, p):
				return node
	return null


# 캐릭터 선택 화면의 좌우 화살표 버튼은 씬에서 숨겨져(visible=false) 있어 터치를 못 받음.
# 부모 화면이 보이는 동안에는 숨겨진 상태 그대로 터치 영역으로 사용한다.
func _hidden_hit_area_ok(node: Node) -> bool:
	if node.name != "next_player" and node.name != "prev_player":
		return false
	if node.get("direction") == null:
		return false
	var parent = node.get_parent()
	return parent != null and parent is CanvasItem and parent.is_visible_in_tree()


func _button_has_point(b, p: Vector2) -> bool:
	var local = b.get_global_transform_with_canvas().affine_inverse().xform(p)
	return Rect2(Vector2.ZERO, b.rect_size).has_point(local)


func _begin_tap(index: int, p: Vector2) -> void:
	_clear_tap()
	var b = _find_button_at(get_tree().root, p)
	if b == null:
		return
	tap_index = index
	tap_button = b
	tap_fired = false
	b.connect("pressed", self, "_on_tap_probe")


func _on_tap_probe() -> void:
	tap_fired = true


func _clear_tap() -> void:
	if tap_button != null and is_instance_valid(tap_button):
		if tap_button.is_connected("pressed", self, "_on_tap_probe"):
			tap_button.disconnect("pressed", self, "_on_tap_probe")
	tap_index = -1
	tap_button = null


func _end_tap(p: Vector2) -> void:
	var b = tap_button
	if b == null or not is_instance_valid(b):
		_clear_tap()
		return
	var inside = _button_has_point(b, p)
	yield(get_tree(), "idle_frame")
	yield(get_tree(), "idle_frame")
	var fired = tap_fired
	if is_instance_valid(b):
		if b.is_connected("pressed", self, "_on_tap_probe"):
			b.disconnect("pressed", self, "_on_tap_probe")
		if inside and not fired and b.focus_mode != Control.FOCUS_NONE:
			if b.is_visible_in_tree():
				b.grab_focus()
			b.emit_signal("pressed")
	if tap_button == b:
		tap_index = -1
		tap_button = null


func _want_dir(want: Dictionary, dir: String) -> void:
	for a in dir_actions[dir]:
		want[a] = true


func _apply() -> void:
	var want = {}
	for i in captures.keys():
		var cap = captures[i]
		if cap["control"] == "stick":
			var z = cap["zone"]
			if z == "stick":
				var v = _stick_vector(_to_window(stick_frame), cap)
				if v.x < -DIGITAL_THRESHOLD:
					_want_dir(want, "left")
				elif v.x > DIGITAL_THRESHOLD:
					_want_dir(want, "right")
				if v.y < -DIGITAL_THRESHOLD:
					_want_dir(want, "up")
				elif v.y > DIGITAL_THRESHOLD:
					_want_dir(want, "down")
			elif z != "":
				_want_dir(want, z)
		else:
			for b in buttons:
				if b[0] == cap["control"]:
					for a in b[3]:
						want[a] = true
	for a in active.keys():
		if not want.has(a):
			Input.action_release(a)
			active.erase(a)
	for a in want.keys():
		if not active.has(a):
			Input.action_press(a)
			active[a] = true
	if canvas:
		canvas.update()


func _white(alpha: float) -> Color:
	return Color(1, 1, 1, clamp(alpha, 0.0, 1.0))


func _capsule(r: Rect2) -> PoolVector2Array:
	var radius = min(r.size.x, r.size.y) * 0.5
	var c = r.position + r.size * 0.5
	var sx = max(r.size.x * 0.5 - radius, 0.0)
	var sy = max(r.size.y * 0.5 - radius, 0.0)
	var pts = PoolVector2Array()
	var n = 16
	if sx > 0.0:
		for i in range(n + 1):
			var a1 = -PI * 0.5 + PI * float(i) / float(n)
			pts.append(c + Vector2(sx, 0) + Vector2(cos(a1), sin(a1)) * radius)
		for j in range(n + 1):
			var a2 = PI * 0.5 + PI * float(j) / float(n)
			pts.append(c - Vector2(sx, 0) + Vector2(cos(a2), sin(a2)) * radius)
	elif sy > 0.0:
		for k in range(n + 1):
			var a3 = PI * float(k) / float(n)
			pts.append(c + Vector2(0, sy) + Vector2(cos(a3), sin(a3)) * radius)
		for m in range(n + 1):
			var a4 = PI + PI * float(m) / float(n)
			pts.append(c - Vector2(0, sy) + Vector2(cos(a4), sin(a4)) * radius)
	else:
		for q in range(n * 2):
			var a5 = TAU * float(q) / float(n * 2)
			pts.append(c + Vector2(cos(a5), sin(a5)) * radius)
	return pts


func _label(text: String, r: Rect2, col: Color) -> void:
	if font == null:
		return
	var size_px = min(r.size.x, r.size.y) * 0.42
	if text.length() > 2:
		size_px = min(r.size.x, r.size.y) * 0.30
	var k = size_px / font.get_height()
	var w = font.get_string_size(text).x * k
	var c = r.position + r.size * 0.5
	var baseline = c.y + (font.get_ascent() - font.get_height() * 0.5) * k
	canvas.draw_set_transform(Vector2(c.x - w * 0.5, baseline), 0.0, Vector2(k, k))
	canvas.draw_string(font, Vector2.ZERO, text, col)
	canvas.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _on_draw() -> void:
	if not shown:
		return
	var bw = 0.6
	var sf = _to_window(stick_frame)
	var c = sf.position + sf.size * 0.5
	var base_size = min(sf.size.x, sf.size.y)
	var radius = base_size * 0.5
	var ring = base_size * STICK_DPAD_RING_RADIUS
	canvas.draw_circle(c, radius, _white(0.10))
	canvas.draw_arc(c, radius, 0.0, TAU, 48, _white(0.38), bw, true)
	canvas.draw_arc(c, ring, 0.0, TAU, 48, _white(0.20), bw, true)
	var pressed_zones = {}
	var knob = c
	for i in captures.keys():
		var cap = captures[i]
		if cap["control"] == "stick":
			if cap["zone"] == "stick":
				knob = c + _stick_delta(sf, cap)
			elif cap["zone"] != "":
				pressed_zones[cap["zone"]] = true
	var arrow_dist = (radius + ring) * 0.5
	var arrow_size = (radius - ring) * 0.3
	var dirs = {"up": Vector2(0, -1), "down": Vector2(0, 1), "left": Vector2(-1, 0), "right": Vector2(1, 0)}
	for key in dirs.keys():
		var dir = dirs[key]
		var tip = c + dir * (arrow_dist + arrow_size)
		var base = c + dir * (arrow_dist - arrow_size)
		var side = Vector2(-dir.y, dir.x) * arrow_size
		var alpha = 0.45
		if pressed_zones.has(key):
			alpha = 0.85
		canvas.draw_colored_polygon(PoolVector2Array([tip, base + side, base - side]), _white(alpha))
	var knob_r = base_size * 0.14
	canvas.draw_circle(knob, knob_r, _white(0.18))
	canvas.draw_arc(knob, knob_r, 0.0, TAU, 32, _white(0.72), bw, true)
	var held = {}
	for i2 in captures.keys():
		held[captures[i2]["control"]] = true
	for b in buttons:
		var r = _to_window(b[2])
		var is_held = held.has(b[0])
		var pts = _capsule(r)
		var fill_a = 0.08
		var line_a = 0.32
		var text_a = 0.85
		if is_held:
			fill_a = 0.35
			line_a = 0.80
			text_a = 1.0
		canvas.draw_colored_polygon(pts, _white(fill_a))
		pts.append(pts[0])
		canvas.draw_polyline(pts, _white(line_a), bw, true)
		_label(b[1], r, _white(text_a))
'''


def patch_overlay():
    path = os.path.join("System", "IOSTouchOverlay.gd")
    write(path, OVERLAY_GD)
    print(f"[ok]   {path} (iOS 가상 패드)")
    proj = read("project.godot")
    if "IOSTouchOverlay=" in proj:
        print("[skip] project.godot (IOSTouchOverlay 이미 등록됨)")
        return
    nl = "\r\n" if "\r\n" in proj else "\n"
    m = re.search(r"^\[autoload\]\s*$", proj, re.M)
    if not m:
        sys.exit("[error] project.godot에 [autoload] 섹션이 없음")
    line = 'IOSTouchOverlay="*res://System/IOSTouchOverlay.gd"'
    proj = proj[: m.end()] + nl + line + proj[m.end():]
    write("project.godot", proj)
    print("[ok]   project.godot += IOSTouchOverlay autoload")


if __name__ == "__main__":
    if not os.path.exists("project.godot"):
        sys.exit("[error] 저장소 루트(project.godot가 있는 곳)에서 실행하세요")
    patch_character_manager()
    patch_spawner()
    patch_project_godot()
    patch_presets()
    patch_overlay()
    apply_korean()
