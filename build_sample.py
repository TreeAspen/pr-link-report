# -*- coding: utf-8 -*-
"""
把一份完整的 EIN 传播报告 PDF 还原成本工具的项目结构，生成 sample.js。
index.html 载入后，「载入示例」得到的就是与原 PDF 逐板块对应的样例。

覆盖：主要通讯社 / 搜索引擎与 AI 数据库 / 新闻数据库 / 独立媒体转载 /
      AGP 刊物 / EIN 各行业频道 / 世界媒体名录 / 社交分享 / 报告摘要。

用法：
    python build_sample.py "STARR PR Report bridge-2026 NYC.pdf"

依赖 logos.js 的图库来给条目配 logo，所以请先跑 extract_logos.py。
"""
import sys, os, re, json, base64, glob

import pymupdf
from extract_logos import (domain_of, registrable, clean_lines, name_and_sub,
                           SKIP_URL, LOC_RE, MANIFEST)

OUT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.js")

# 深色标题条上的白字（原报告的一级板块）
HEADER_SIZE, WHITE = 10.5, 16777215
# 名录 / 频道的三栏文字所在的 x 位置
COL_X = (50.9, 231.2, 411.4)
SUBHEAD = re.compile(r"(.+?)\s+Distribution Channel$")

# 版式；标题一律沿用原报告的英文原文，不做任何增删
LAYOUT = {
    "Major newswires":               "t4",
    "Search engines & AI databases": "t4",
    "News Databases":                "t3",
    "Major News Platforms":          "c2",
    "Affinity Group Publications":   "c2",
}


# ------------------------------------------------------------------ 取文字流
def text_stream(doc, last_page):
    """(page, y, x, text, size, white) 的有序流；跨页按页码+y 排序"""
    out = []
    for pno in range(min(last_page, len(doc))):
        for blk in doc[pno].get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if not txt:
                    continue
                s0 = ln["spans"][0]
                out.append(dict(p=pno, y=round(ln["bbox"][1], 1), x=round(ln["bbox"][0], 1),
                                t=txt, sz=round(s0["size"], 1), white=s0["color"] == WHITE))
    out.sort(key=lambda i: (i["p"], i["y"], i["x"]))
    return out


def headers_of(stream):
    """一级板块标题（白字）+ 明确补上不带底色的 Report Summary"""
    hs, buf = [], None
    for it in stream:
        if it["white"] and it["sz"] == HEADER_SIZE:
            if buf and buf["p"] == it["p"] and abs(buf["y"] - it["y"]) < 2:
                buf["t"] += " " + it["t"]                  # 同一行被拆成多段
                continue
            if buf:
                hs.append(buf)
            buf = dict(it)
        elif it["t"] == "Report Summary" and it["sz"] >= 10:
            if buf:
                hs.append(buf); buf = None
            hs.append(dict(it))
    if buf:
        hs.append(buf)
    return [h for h in hs if not h["t"].startswith(("New distribution", "Download PDF"))]


def between(stream, start, end, pred=None):
    """取 [start, end) 之间的文字项；start/end 为 (page, y)"""
    out = []
    for it in stream:
        k = (it["p"], it["y"])
        if k < start or (end and k >= end):
            continue
        if pred and not pred(it):
            continue
        out.append(it)
    return out


def merge_wraps(items):
    """三栏文字里换行的条目合并回一条，并按「行优先」还原原顺序"""
    cols = {}
    for it in items:
        c = min(range(len(COL_X)), key=lambda i: abs(COL_X[i] - it["x"]))
        cols.setdefault(c, []).append(it)
    merged = []
    for c, lst in cols.items():
        lst.sort(key=lambda i: (i["p"], i["y"]))
        cur = None
        for it in lst:
            if cur and it["p"] == cur["p"] and 0 < it["y"] - cur["ylast"] < 12:
                cur["t"] += " " + it["t"]                  # 续行
                cur["ylast"] = it["y"]
            else:
                cur = dict(t=it["t"], p=it["p"], y=it["y"], ylast=it["y"], c=c)
                merged.append(cur)
    merged.sort(key=lambda m: (m["p"], round(m["y"] / 6), m["c"]))   # 行优先
    return [m["t"] for m in merged]


# ------------------------------------------------------------------ 取链接
def links_of(doc, last_page):
    out = []
    for pno in range(min(last_page, len(doc))):
        pg = doc[pno]
        for l in pg.get_links():
            uri = l.get("uri")
            if not uri:
                continue
            r = l["from"]
            lines = clean_lines(pg.get_text("text", clip=r))
            if not lines:
                r2 = pymupdf.Rect(r.x0 - 150, r.y0 - 6, r.x1 + 10, r.y1 + 6)
                lines = clean_lines(pg.get_text("text", clip=r2))
            name, sub = name_and_sub(lines)
            out.append(dict(p=pno, y=round(r.y0, 1), x=round(r.x0, 1),
                            uri=uri, name=name, sub=sub, host=domain_of(uri)))
    out.sort(key=lambda i: (i["p"], round(i["y"] / 6), i["x"]))

    # 折行的链接在 PDF 里是多个注释（每行一个），指向同一 URL —— 按「页 + URL」归并回一条。
    # 不能只合并相邻项：排序是行优先的，同一链接的两行会被其他栏目的链接隔开。
    groups = {}
    for lk in out:
        groups.setdefault((lk["p"], lk["uri"]), []).append(lk)
    merged = []
    for frags in groups.values():
        frags.sort(key=lambda i: (i["y"], i["x"]))
        head = dict(frags[0])
        for f in frags[1:]:
            if f["name"] and f["name"] not in head["name"]:
                head["name"] = (head["name"] + " " + f["name"]).strip()
            head["sub"] = head["sub"] or f["sub"]
        merged.append(head)
    merged.sort(key=lambda i: (i["p"], round(i["y"] / 6), i["x"]))
    return merged


def row(lk, lib_hosts):
    key = lk["host"] if lk["host"] in lib_hosts else registrable(lk["host"])
    return {"name": lk["name"] or key, "sub": lk["sub"], "url": lk["uri"],
            "img": "", "logo": ("lib:" + key) if key in lib_hosts else ""}


# ------------------------------------------------------------------ 报告摘要
def build_summary(doc, stream):
    pg = doc[11] if len(doc) > 11 else doc[-1]
    txt = pg.get_text("text")

    def grab(pat, default=""):
        m = re.search(pat, txt)
        return m.group(1).strip() if m else default

    title_stat = grab(r"Title:\s*([^\n]+)")
    text_stat  = grab(r"Text:\s*([^\n]+)")
    # 标题原文 = Title 行之后、Text 行之前
    seg = re.search(r"Title:[^\n]*\n(.*?)\nText:", txt, re.S)
    title_text = " ".join(seg.group(1).split()) if seg else ""
    seg = re.search(r"Text:[^\n]*\n(.*?)\nKeyword Anchor", txt, re.S)
    excerpt = " ".join(seg.group(1).split()) if seg else ""

    anchors, others, images = [], [], []
    seg = re.search(r"Keyword Anchor Text Links:[^\n]*\n(.*?)(?:\nOther Links:|\Z)", txt, re.S)
    if seg:
        line = " ".join(seg.group(1).split())
        m = re.match(r"(.*?)\s*-\s*(https?://\S+)", line)
        if m:
            anchors.append({"text": m.group(1), "url": m.group(2)})
        elif line:
            anchors.append({"text": line, "url": ""})

    for l in pg.get_links():                                  # 其他链接
        u = l.get("uri") or ""
        if u and not SKIP_URL.search(u) and "aaiea" not in u:
            continue
    others = sorted({(l.get("uri") or "").rstrip("/") for l in pg.get_links()
                     if l.get("uri") and "ssl.cf2" not in l["uri"]
                     and "einpresswire.com/press-releases/report-" not in l["uri"]
                     and not re.search(r"facebook|x\.com|linkedin|bsky", l["uri"])})
    others = [o for o in others if o]

    # 嵌入图片：缩略图 + Name/Caption
    fulls = [l for l in pg.get_links() if l.get("uri") and "ssl.cf2" in l["uri"]]
    thumbs = [im for im in pg.get_image_info(xrefs=True)
              if im.get("width", 0) > 20 and im["bbox"][1] > 400]
    thumbs.sort(key=lambda im: im["bbox"][1])
    blocks = re.findall(r"Name:\s*(.*?)\s*Caption:\s*(.*?)\s*Alt Text:",
                        " ".join(txt.split()))
    for i, (nm, cap) in enumerate(blocks):
        rec = {"name": nm, "caption": cap, "url": fulls[i]["uri"] if i < len(fulls) else "", "img": ""}
        if i < len(thumbs):
            pix = pymupdf.Pixmap(doc, thumbs[i]["xref"])
            if pix.n - pix.alpha >= 4:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            rec["img"] = "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()
        images.append(rec)

    return {"titleStat": title_stat, "titleText": title_text,
            "textStat": text_stat, "textExcerpt": excerpt,
            "anchors": anchors, "others": others, "images": images,
            "videos": int(grab(r"Embedded Videos:\s*(\d+)", "0"))}


# ------------------------------------------------------------------ 主流程
def build(pdf):
    doc = pymupdf.open(pdf)
    last = min(12, len(doc))                                 # 第 13 页起是自家提案，不属于报告
    stream = text_stream(doc, last)
    heads = headers_of(stream)
    links = links_of(doc, last)

    lib_hosts = set()
    if os.path.exists(MANIFEST):
        for e in json.load(open(MANIFEST, encoding="utf-8")):
            if e.get("file"):
                lib_hosts.add(e["key"])

    bounds = [(h["p"], h["y"]) for h in heads] + [(10 ** 6, 0)]
    sections = []

    for i, h in enumerate(heads):
        start, end = (h["p"], h["y"]), bounds[i + 1]
        title = h["t"].strip()
        mine = [l for l in links if start < (l["p"], l["y"]) < end and not SKIP_URL.search(l["uri"])]

        # 板块说明：标题与首个卡片之间的正文
        first_y = min([(l["p"], l["y"]) for l in mine], default=end)
        # 说明文字在最左（x≈35.6）；子标题在 43.5、三栏名单在 50.9 起，都要排除
        desc = " ".join(t["t"] for t in between(stream, start, first_y,
                        lambda it: it["x"] < 42 and it["sz"] < 9 and not it["white"])).strip()

        if title.startswith("World Media Directory"):
            subs = between(stream, start, end, lambda it: SUBHEAD.match(it["t"]))
            regions = []
            for j, sh in enumerate(subs):
                s2 = (sh["p"], sh["y"])
                e2 = (subs[j + 1]["p"], subs[j + 1]["y"]) if j + 1 < len(subs) else end
                meta = between(stream, s2, e2, lambda it: it["x"] < 70)
                region = next((m["t"] for m in meta if 60 < m["x"] < 70), SUBHEAD.match(sh["t"]).group(1))
                count = next((m["t"] for m in meta if "targets" in m["t"]), "")
                names = merge_wraps(between(stream, s2, e2,
                                    lambda it: any(abs(it["x"] - c) < 4 for c in COL_X)))
                flag = {"China": "🇨🇳", "United States": "🇺🇸"}.get(region, "🗽")
                regions.append({"flag": flag, "name": region, "count": count,
                                "url": "", "names": names})
            sections.append({"type": "directory", "title": title,
                             "desc": desc, "regions": regions})
            continue

        if title.startswith("Boost your reach"):
            soc = [l for l in links if start < (l["p"], l["y"]) < end
                   and re.search(r"facebook|x\.com|linkedin|bsky", l["uri"])]
            names = ["Facebook", "X/Twitter", "LinkedIn", "Bluesky"]
            sections.append({"type": "social", "title": title, "desc": desc,
                             "rows": [{"name": names[k] if k < len(names) else l["name"],
                                       "sub": "", "url": l["uri"], "img": "", "logo": ""}
                                      for k, l in enumerate(soc)]})
            continue

        if title.startswith("Report Summary"):
            sections.append({"type": "summary", "title": title,
                             "desc": "", "summary": build_summary(doc, stream)})
            continue

        if title.startswith("EIN Presswire newswires"):
            # 原报告里这是一个大标题条 + 若干灰底子盒（各行业频道），保持同样的层级
            subs = between(stream, start, end, lambda it: SUBHEAD.match(it["t"]) and it["x"] < 70)
            head_rows = [l for l in mine if not subs or (l["p"], l["y"]) < (subs[0]["p"], subs[0]["y"])]
            if head_rows:                                    # 频道之前那几个 AGP 方块，仍属上一板块
                sections[-1]["rows"].extend(row(l, lib_hosts) for l in head_rows)
            groups = []
            for j, sh in enumerate(subs):
                s2 = (sh["p"], sh["y"])
                e2 = (subs[j + 1]["p"], subs[j + 1]["y"]) if j + 1 < len(subs) else end
                names = [{"n": l["name"], "u": l["uri"]} for l in links
                         if s2 < (l["p"], l["y"]) < e2 and not SKIP_URL.search(l["uri"])]
                if names:
                    groups.append({"flag": "", "name": sh["t"], "count": "", "url": "", "names": names})
            sections.append({"type": "directory", "title": title, "desc": desc, "regions": groups})
            continue

        if mine:
            sections.append({"type": "links", "title": title, "desc": desc,
                             "layout": LAYOUT.get(title, "c2"),
                             "rows": [row(l, lib_hosts) for l in mine]})

    # 页头信息：标题取报告摘要里的原文，日期与开篇段落取首页
    p1 = doc[0].get_text("text")
    summary = next((s["summary"] for s in sections if s["type"] == "summary"), None)
    title_txt = (summary or {}).get("titleText", "")
    if not title_txt:                                        # 兜底：取 Distributed on 之前的两行
        m = re.search(r"([^\n]+\n[^\n]+)\nDistributed on", p1)
        title_txt = " ".join(m.group(1).split()) if m else "Press Release Distribution Report"
    m = re.search(r"Distributed on ([^\n]+)", p1)
    subtitle = "Distributed on " + m.group(1).strip() if m else ""
    m = re.search(r"(Congratulations!.*?accomplished\.)", p1, re.S)
    intro = " ".join(m.group(1).split()) if m else \
            "Congratulations! Your press release made it into today's news cycle."

    proj = {
        "brand": "ETB STARR CONSULTING",
        "tagline": "Brand Communications & Media Advisory",
        "logo": "", "cover": "", "coverCap": "",
        "title": title_txt or "Press Release Distribution Report",
        "subtitle": subtitle,
        "intro": " ".join(intro.split()),
        "footer": "contact@starrconsulting.com",
        "navy": "#1b2a4e", "accent": "#e2245e",
        "toc": True, "linkIndex": False,
        "sections": [{**{"id": "s%d" % k, "desc": "", "layout": "c2", "hero": "", "heroCap": "",
                         "rows": [], "regions": [], "summary": None}, **s}
                     for k, s in enumerate(sections)],
    }
    doc.close()
    return proj


if __name__ == "__main__":
    args = [p for a in sys.argv[1:] for p in glob.glob(a)]
    if not args:
        args = sorted(glob.glob(os.path.join(os.path.dirname(OUT_JS), "*.pdf")))
    if not args:
        print("用法：python build_sample.py <报告.pdf>")
        sys.exit(1)

    proj = build(args[0])
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("/* 样例项目 —— 由 build_sample.py 从传播报告 PDF 还原，请勿手改 */\n"
                "window.SAMPLE_REPORT = " + json.dumps(proj, ensure_ascii=False) + ";\n")

    n_rows = sum(len(s["rows"]) for s in proj["sections"])
    n_names = sum(len(g["names"]) for s in proj["sections"] for g in s.get("regions") or [])
    print(f"✓ {os.path.basename(args[0])}")
    for s in proj["sections"]:
        extra = (f"{len(s['rows'])} 条" if s["type"] == "links" else
                 f"{len(s.get('regions') or [])} 个地区 / {sum(len(g['names']) for g in s.get('regions') or [])} 家" if s["type"] == "directory" else
                 s["type"])
        print(f"   · {s['title'][:44]:46} {extra}")
    print(f"\n共 {len(proj['sections'])} 个区块 / {n_rows} 条链接 / 名录 {n_names} 家")
    print(f"→ sample.js（{os.path.getsize(OUT_JS)/1024:.0f} KB）  刷新 index.html 后点「载入示例」")
