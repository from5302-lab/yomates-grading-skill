#!/usr/bin/env python3
"""빨간 펜 첨삭본 만들기 (우리 학원 채점 규칙 스킬 4-2단계).

쓰는 법:  python3 redpen.py 표시.json 결과.png

표시.json 모양 (값은 예시가 아니라 칸 이름만):
{
  "사진": "답안지 사진 경로",
  "대표색": "#e0242c",            # 설정의 '빨간 펜 색'(비면 대표 색, 그것도 비면 #e0242c)
  "배점방식": "개수",              # "개수"(기본) 또는 "배점"
  "문항": [ {"번호": 1, "결과": "O|X|△|보류", "배점": 7, "받은점수": 7}, ... ],
  "표시": [ {"종류": "O", "x":0, "y":0, "rx":0, "ry":0},     # 맞음 동그라미
           {"종류": "X", "x":0, "y":0},                     # 틀림 빗금
           {"종류": "△", "x":0, "y":0},                     # 부분 정답
           {"종류": "밑줄", "x1":0, "x2":0, "y":0},          # 틀린 낱말 밑줄
           {"종류": "글", "x":0, "y":0, "크기":52, "글":"→ 고친 답"},
           {"종류": "점수", "x":0, "y":0},                   # 글이 없으면 문항으로 계산
           {"종류": "총평", "x":0, "y":0, "글":"실수 패턴 한 줄"} ],
  "고친 답 목록": ["놓을 빈자리가 없을 때만, 사진 아래에 붙는 줄"]
}
좌표는 사진 픽셀. 글자 크기와 선 굵기는 사진 폭 1500px 기준 값이고, 사진 폭에 맞춰 늘거나 준다.
크레딧 0: 컴퓨터 안 크롬 headless로만 그린다. 다 쓴 크롬은 닫는다.
"""
import html, json, os, re, shutil, struct, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/nanumpenscript/NanumPenScript-Regular.ttf"
FONT = os.path.expanduser("~/.cache/yomates-redpen/NanumPenScript-Regular.ttf")
CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           "google-chrome", "chromium"]


def image_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        f.seek(2)
        while True:  # JPEG
            marker, = struct.unpack(">H", f.read(2))
            size, = struct.unpack(">H", f.read(2))
            if 0xFFC0 <= marker <= 0xFFC3:
                f.read(1); h, w = struct.unpack(">HH", f.read(4)); return w, h
            f.seek(size - 2, 1)


def font_path():
    if not os.path.exists(FONT):  # 무료 OFL 글꼴을 한 번만 받는다
        os.makedirs(os.path.dirname(FONT), exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, FONT)
    return FONT


def score_text(d):
    qs = [q for q in d.get("문항", []) if q["결과"] != "보류"]
    held = len(d.get("문항", [])) - len(qs)
    if d.get("배점방식", "개수") == "배점":
        got = sum(q.get("받은점수", 0) for q in qs); full = sum(q.get("배점", 0) for q in qs)
        t = f"{got}/{full}"
    else:  # 맞은 개수 ÷ 총 문항 × 100, 부분 정답은 틀림
        ok = sum(1 for q in qs if q["결과"] == "O")
        t = f"{ok}/{len(qs)} · {round(ok / len(qs) * 100) if qs else 0}점"
    return t + (f" (보류 {held})" if held else "")


def marks(d, k, color):
    out = []
    for m in d.get("표시", []):
        t = m["종류"]
        if t == "O":
            x, y = m["x"], m["y"]
            out.append(f'<ellipse cx="{x}" cy="{y}" rx="{m["rx"]}" ry="{m["ry"]}" fill="none" stroke="{color}" stroke-width="{6*k:.1f}" transform="rotate(-4 {x} {y})"/>')
        elif t == "X":
            x, y, a, b = m["x"], m["y"], 30 * k, 42 * k
            out.append(f'<path d="M{x-a:.0f} {y+b:.0f} L{x+a:.0f} {y-b:.0f}" stroke="{color}" stroke-width="{9*k:.1f}" stroke-linecap="round"/>')
        elif t == "△":
            x, y, r = m["x"], m["y"], m.get("r", 44) * k
            out.append(f'<path d="M{x} {y-r:.0f} L{x+r:.0f} {y+r*0.75:.0f} L{x-r:.0f} {y+r*0.75:.0f} Z" fill="none" stroke="{color}" stroke-width="{7*k:.1f}" stroke-linejoin="round"/>')
        elif t == "밑줄":
            x1, x2, y = m["x1"], m["x2"], m["y"]
            out.append(f'<path d="M{x1} {y} Q{(x1+x2)/2} {y+10*k:.0f} {x2} {y}" stroke="{color}" stroke-width="{5*k:.1f}" fill="none" stroke-linecap="round"/>')
        elif t in ("글", "점수", "총평"):
            size = m.get("크기", {"글": 52, "점수": 100, "총평": 54}[t])
            text = m.get("글") or (score_text(d) if t == "점수" else "")
            out.append(f'<text class="pen" x="{m["x"]}" y="{m["y"]}" font-size="{size*k:.0f}" stroke-width="{7*k:.1f}">{html.escape(text)}</text>')
    return out


def fixes(d, k, top, w):
    rows = d.get("고친 답 목록", [])
    if not rows:
        return [], 0
    line = 64 * k
    out = [f'<text class="pen" x="{60*k:.0f}" y="{top+line:.0f}" font-size="{52*k:.0f}" stroke-width="{7*k:.1f}">고친 답</text>']
    for i, r in enumerate(rows):
        out.append(f'<text class="pen" x="{60*k:.0f}" y="{top+line*(i+2):.0f}" font-size="{48*k:.0f}" stroke-width="{7*k:.1f}">{html.escape(r)}</text>')
    return out, int(line * (len(rows) + 2.5))


def overlap_warnings(d, k):
    """글 표시 자리에 원래 글씨(어두운 점)가 많으면 알려 준다. PIL이 없으면 건너뛴다."""
    try:
        from PIL import Image
    except ImportError:
        return ["(PIL이 없어 겹침 자동 검사는 건너뜀. 그림을 열어 눈으로 확인)"]
    im = Image.open(d["사진"]).convert("L"); W, H = im.size; px = im.load(); warn = []
    for m in d.get("표시", []):
        if m["종류"] not in ("글", "점수", "총평"):
            continue
        size = m.get("크기", {"글": 52, "점수": 100, "총평": 54}[m["종류"]]) * k
        text = m.get("글") or score_text(d)
        x0, y1 = int(m["x"]), int(m["y"] + size * 0.2)
        x1, y0 = int(min(W - 1, x0 + len(text) * size * 0.48)), int(max(0, m["y"] - size * 0.8))
        if y0 >= H:
            continue  # 사진 아래 덧붙인 자리
        y1 = min(H - 1, y1); dark = tot = 0
        for yy in range(y0, y1, 3):
            for xx in range(x0, x1, 3):
                tot += 1; dark += px[xx, yy] < 140
        if tot and dark / tot > 0.02:
            warn.append(f"겹침 의심 {dark/tot:.0%}: {text}")
        if x1 >= W - 1:
            warn.append(f"오른쪽 끝을 넘을 수 있음: {text}")
    return warn


def chrome():
    for c in CHROMES:
        if os.path.exists(c) or shutil.which(c):
            return c
    sys.exit("크롬을 찾지 못했어요. 크롬을 설치하거나 CHROMES에 경로를 더해 주세요.")


def main(src, out):
    d = json.load(open(src, encoding="utf-8"))
    photo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(src)), d["사진"]))
    d["사진"] = photo
    w, h = image_size(photo); k = w / 1500
    color = d.get("대표색") or "#e0242c"
    extra, add_h = fixes(d, k, h, w)
    tpl = open(os.path.join(HERE, "redpen.html"), encoding="utf-8").read()
    page = (tpl.replace("{{글꼴}}", "file://" + font_path()).replace("{{사진}}", "file://" + photo)
               .replace("{{사진세로}}", str(h)).replace("{{세로}}", str(h + add_h)).replace("{{가로}}", str(w))
               .replace("{{대표색}}", color).replace("{{표시}}", "\n".join(marks(d, k, color) + extra)))
    left = re.findall(r"\{\{[^}]+\}\}", page)
    if left:
        sys.exit(f"채우지 않은 자리 표시가 남았어요: {left}")
    work = tempfile.mkdtemp(prefix="redpen-")
    page_path = os.path.join(work, "page.html"); open(page_path, "w", encoding="utf-8").write(page)
    profile = os.path.join(work, "profile")
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                    "--force-device-scale-factor=1", f"--window-size={w},{h+add_h}", "--virtual-time-budget=3000",
                    f"--screenshot={os.path.abspath(out)}", "file://" + page_path], check=True, capture_output=True)
    time.sleep(0.5)  # 다 쓴 크롬을 닫는다: 이 작업 폴더로 띄운 크롬이 남아 있으면 끈다
    if os.name != "nt":
        subprocess.run(["pkill", "-f", profile], capture_output=True)
        still = subprocess.run(["pgrep", "-f", profile], capture_output=True, text=True).stdout.strip()
        print("남은 크롬:", "없음" if not still else still)
    shutil.rmtree(work, ignore_errors=True)
    print("점수:", score_text(d))
    for line in overlap_warnings(d, k):
        print(line)
    print("저장:", out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("python3 redpen.py 표시.json 결과.png")
    main(sys.argv[1], sys.argv[2])
