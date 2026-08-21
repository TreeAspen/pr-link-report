# -*- coding: utf-8 -*-
"""
从 EIN Presswire 传播报告 PDF 中提取媒体 Logo，并与链接域名、媒体名称关联，
生成 logos.js（供 index.html 直接使用）+ logos_manifest.json（人工核对用）。

用法：
    python extract_logos.py "STARR PR Report bridge-2026 NYC.pdf"
    python extract_logos.py *.pdf            # 多份报告一起跑，图库自动合并去重

多跑几份不同的报告，图库会越攒越全；已有条目不会被空数据覆盖。
"""
import sys, os, re, json, glob, base64, io
from collections import OrderedDict

import pymupdf
from PIL import Image

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR  = os.path.join(OUT_DIR, "logos")
MANIFEST  = os.path.join(OUT_DIR, "logos_manifest.json")
JS_OUT    = os.path.join(OUT_DIR, "logos.js")

MAX_W, MAX_H = 260, 90        # 图库里 logo 的最大尺寸
MIN_W, MIN_H = 16, 10         # 小于此尺寸视为装饰性图元，丢弃

# 这些是版式文案，不是媒体名
NOISE = re.compile(
    r"^(click on|here (is|are)|explore the|your press release|congratulations|"
    r"millions of|ein presswire|note:|affinity group|below is|based on the|"
    r"new distribution|view tracking|download pdf|distributed on|boost your|"
    r"share your press|major newswires|search engines|news databases|"
    r"major news platforms|world media directory|report summary|"
    r"\d+ targets|https?://)", re.I)

LOC_RE = re.compile(r"^[A-Z][\w .'\-]+ \([A-Z]{2}\)$")     # Buffalo (NY)

# EIN 自家的功能链接 / 社交分享链接，不是媒体转载，排除
SKIP_URL = re.compile(
    r"einpresswire\.com/(pricing|contact|article|article-print|press-releases/report-|"
    r"newsroom/?$|world-media-directory|distribution|help|login|signup|plans)|"
    r"//(www\.)?(facebook|twitter|x|linkedin|bsky|instagram|pinterest)\.(com|app)|"
    r"/(sharer|intent|share)\b|/share\?|mailto:|"
    r"rackcdn\.com|cloudfront\.net|\.s3[.-]|/full-size|einpresswire\.com/?$", re.I)

# 只有 logo 没有文字的方块，名称按域名补
NAME_FIX = {
    "google.com": "Google", "news.google.com": "Google News", "chat.openai.com": "ChatGPT",
    "search.yahoo.com": "Yahoo", "bing.com": "Bing", "bloomberg.com": "Bloomberg Terminal",
    "muckrack.com": "Muck Rack", "newsedge.com": "Moody's NewsEdge", "navigaglobal.com": "Naviga",
    "menafn.com": "MENAFN", "crunchbase.com": "Crunchbase", "apnews.com": "AP News",
}


def name_from_domain(host):
    if host in NAME_FIX:
        return NAME_FIX[host]
    core = registrable(host).rsplit(".", 1)[0] if host else ""
    return core.replace("-", " ").title() if core else ""


# ---------------------------------------------------------------- 域名
def domain_of(url: str) -> str:
    m = re.match(r"https?://([^/?#]+)", url or "", re.I)
    if not m:
        return ""
    host = m.group(1).lower().split(":")[0]
    host = re.sub(r"^(www|www\d|m|amp|mobile|en)\.", "", host)
    return host


def registrable(host: str) -> str:
    """粗略取可注册域：news.google.com -> google.com；bbc.co.uk -> bbc.co.uk"""
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    two = ".".join(parts[-2:])
    if parts[-2] in ("co", "com", "net", "org", "gov", "edu", "ac") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return two


# ---------------------------------------------------------------- 图片
def logo_area(page, rect):
    """卡片内文字右侧（或全部，若无文字）的区域，即 logo 所在处；太窄则返回 None"""
    xs = []
    d = page.get_text("dict", clip=rect)
    for blk in d.get("blocks", []):
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                if sp.get("text", "").strip():
                    xs.append(sp["bbox"][2])
    if xs:
        left = max(xs) + 4                      # 文字最右边界 + 间隙
    else:
        left = rect.x0 + 3                      # 纯 logo 方块：整格
    box = pymupdf.Rect(left, rect.y0 + 3, rect.x1 - 3, rect.y1 - 3)
    if box.width < 14 or box.height < 9:
        return None
    return box


def normalize(png: bytes):
    """裁掉空白、缩放到图库尺寸；整块空白（无 logo）返回 None"""
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    alpha = im.split()[3]
    if alpha.getextrema()[0] < 255:                        # 有透明通道：按不透明区域裁
        box = im.getbbox()
    else:                                                  # 无透明：按非白区域裁
        gray = im.convert("L").point(lambda p: 0 if p > 246 else 255)
        box = gray.getbbox()
    if not box:                                            # 全白 → 这张卡片没有 logo
        return None, 0, 0
    im = im.crop(box)
    w, h = im.size
    if w < MIN_W or h < MIN_H:
        return None, w, h
    sc = min(MAX_W / w, MAX_H / h, 1.0)
    if sc < 1.0:
        im = im.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.LANCZOS)

    best = None                                            # 真彩 / 调色板两种编码取小的那个
    for cand in (im, im.convert("RGB").quantize(colors=128, method=Image.MEDIANCUT)):
        buf = io.BytesIO()
        try:
            cand.save(buf, "PNG", optimize=True)
        except Exception:
            continue
        if best is None or len(buf.getvalue()) < len(best):
            best = buf.getvalue()
    return best, im.size[0], im.size[1]


# ---------------------------------------------------------------- 文本
def clean_lines(text):
    out = []
    for ln in (text or "").splitlines():
        ln = " ".join(ln.split())
        if not ln or len(ln) > 70 or NOISE.match(ln):
            continue
        out.append(ln)
    return out


def name_and_sub(lines):
    """遇到地区行为止的都算名称（卡片里的长名称会折行，如 New York / Newswire）"""
    if not lines:
        return "", ""
    parts, sub = [], ""
    for ln in lines:
        if parts and (LOC_RE.match(ln) or (len(ln) < 40 and "(" in ln)):
            sub = ln
            break
        parts.append(ln)
    return " ".join(parts[:3]).strip(), sub


def slug(s):
    s = re.sub(r"[^\w一-龥]+", "_", s, flags=re.U).strip("_")
    return (s or "logo")[:48]


# ---------------------------------------------------------------- 主流程
def harvest(path, lib):
    doc = pymupdf.open(path)
    stats = {"links": 0, "with_logo": 0, "text_only": 0, "skipped": 0}

    for pno in range(len(doc)):
        page = doc[pno]
        links = [l for l in page.get_links() if l.get("uri")]
        if not links:
            continue
        try:
            imgs = page.get_image_info(xrefs=True)
        except Exception:
            imgs = []

        for l in links:
            uri = l["uri"]
            if SKIP_URL.search(uri):
                stats["skipped"] += 1
                continue
            host = domain_of(uri)
            r = l["from"]
            stats["links"] += 1

            # --- 该链接框内的文字
            lines = clean_lines(page.get_text("text", clip=r))
            if not lines:                                   # 文字在框外：向左右各扩一点再找
                r2 = pymupdf.Rect(r.x0 - 150, r.y0 - 6, r.x1 + 10, r.y1 + 6)
                lines = clean_lines(page.get_text("text", clip=r2))
            name, sub = name_and_sub(lines)

            # --- logo 区域 = 卡片内文字右侧的剩余部分
            # 报告里的 logo 有三种画法：位图、内联图、矢量图形；按坐标栅格化可以一并拿下。
            # （卡片白色底框本身也是一张图，按 xref 取图会误取到它，故不走 xref 路线。）
            logo_rect = logo_area(page, r)

            key = host or slug(name).lower()
            if not key:
                continue
            entry = lib.setdefault(key, {
                "key": key, "name": "", "sub": "", "domains": [], "file": "", "w": 0, "h": 0
            })
            if name and (not entry["name"] or len(name) > len(entry["name"]) and len(name) < 45):
                entry["name"] = name
            if sub and not entry["sub"]:
                entry["sub"] = sub
            # 顺序必须确定：完整域名在前，可注册域在后（logos.js 用首个域名做 key）
            for d in (host, registrable(host)):
                if d and d not in entry["domains"]:
                    entry["domains"].append(d)

            if logo_rect and not entry["file"]:
                png = page.get_pixmap(clip=logo_rect, dpi=200).tobytes("png")
                if png:
                    data, w, h = normalize(png)
                    if data:
                        base_fn = slug(entry["name"] or key)
                        fn, i = base_fn + ".png", 1
                        while used_files.get(fn, key) != key:      # 同名不同家才加后缀
                            fn = f"{base_fn}_{i}.png"; i += 1
                        used_files[fn] = key
                        with open(os.path.join(LOGO_DIR, fn), "wb") as f:
                            f.write(data)
                        entry.update(file=fn, w=w, h=h)
                        stats["with_logo"] += 1
                    else:
                        stats["text_only"] += 1
            elif not logo_rect:
                stats["text_only"] += 1

    doc.close()
    return stats


def build_js(lib):
    items = []
    total = 0
    for e in sorted(lib.values(), key=lambda x: x["name"] or x["key"]):
        if not e["name"]:                                   # 纯 logo 方块：名称按域名补
            e["name"] = name_from_domain(e["key"])
        rec = {"n": e["name"] or e["key"], "d": e["domains"]}
        if e.get("sub"):
            rec["s"] = e["sub"]
        if e.get("file"):
            p = os.path.join(LOGO_DIR, e["file"])
            if os.path.exists(p):
                b = open(p, "rb").read()
                total += len(b)
                rec["i"] = "data:image/png;base64," + base64.b64encode(b).decode()
                rec["w"], rec["h"] = e["w"], e["h"]
        items.append(rec)
    js = ("/* 媒体 Logo 图库 —— 由 extract_logos.py 从传播报告 PDF 自动生成，请勿手改 */\n"
          "window.LOGO_LIB = " + json.dumps(items, ensure_ascii=False) + ";\n")
    with open(JS_OUT, "w", encoding="utf-8") as f:
        f.write(js)
    return len(items), sum(1 for i in items if "i" in i), total


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        pdfs = sorted(glob.glob(os.path.join(OUT_DIR, "*.pdf")))
        if not pdfs:
            print("用法：python extract_logos.py <报告.pdf> [更多.pdf ...]")
            print("（或把 PDF 放到本脚本同一目录后直接运行）")
            sys.exit(1)
    else:
        pdfs = [p for a in args for p in glob.glob(a)]

    os.makedirs(LOGO_DIR, exist_ok=True)

    lib = {}
    if os.path.exists(MANIFEST):                            # 增量合并历史结果
        try:
            lib = {e["key"]: e for e in json.load(open(MANIFEST, encoding="utf-8"))}
            print(f"已载入现有图库：{len(lib)} 条")
        except Exception:
            pass
    used_files = {e["file"]: e["key"] for e in lib.values() if e.get("file")}

    for p in pdfs:
        st = harvest(p, lib)
        print(f"✓ {os.path.basename(p)}：媒体链接 {st['links']} 个（跳过功能链接 {st['skipped']} 个），"
              f"新提取 logo {st['with_logo']} 张，纯文字条目 {st['text_only']} 个")

    json.dump(list(lib.values()), open(MANIFEST, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n, withimg, size = build_js(lib)
    print(f"\n图库共 {n} 家媒体，其中 {withimg} 家带 logo")
    print(f"→ logos.js  ({size/1024:.0f} KB 内嵌图片)")
    print(f"→ logos_manifest.json（名称/域名对照表，可手工订正后重跑本脚本重建 logos.js）")
    print(f"→ logos/ 目录：单张 PNG 原图")
    print("\n刷新 index.html 即可生效：粘贴链接会自动配上对应 logo。")
