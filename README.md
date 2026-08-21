# PR Link Report Builder · 新闻稿传播报告生成器

把 Excel 表格或一串链接，变成一份带可点击超链接、媒体 Logo 和页面截图的传播报告 PDF。
单文件、纯浏览器运行，不需要服务器，不需要联网。

从 EIN Presswire 之类的分发报告 PDF 中**自动提取媒体 Logo 并与域名建立对应关系**，
之后只要粘贴转载链接，媒体名称、所在地区、Logo 就会自动补全。

---

## 快速开始

```bash
git clone <your-repo-url>
cd pr-link-report
```

直接双击 `index.html` 即可使用。要启用「粘贴链接自动出图」和完整样例，再做一步：

```bash
pip install pymupdf pillow

# 把你的传播报告 PDF 放进本目录，然后：
python extract_logos.py      # 建立 Logo 图库  → logos.js
python build_sample.py       # 还原完整样例    → sample.js
```

刷新 `index.html`，侧栏会显示「Logo 图库：N 家媒体 / M 张 logo」。

---

## 功能

**批量导入**

- 从 Excel / Google Sheets 直接 `Ctrl+V`，自动识别列
- 认得**单元格自带的超链接**（不必单独准备 URL 列）
- 表里有「分组」列时，一次粘贴自动拆成多个板块
- 只粘一列链接也行——其余字段由 Logo 图库补全

**Logo 图库**

`extract_logos.py` 按 PDF 的链接注释坐标定位每张媒体卡片，取出卡片内的 Logo、
媒体名称、所在地区，与跳转域名建立对应关系。

位图、内联图、**矢量图形**三种画法通吃：按坐标栅格化 Logo 区域，自动裁白边、
择优编码。全白区域判空跳过。多跑几份报告，图库自动合并去重、越攒越全。

匹配顺序：完整域名 → 逐级去子域 → 可注册域 → 媒体名称。`www.` / `m.` / `amp.` 自动忽略。

**版式**（对应原报告的各类板块）

| 类型 | 说明 |
|---|---|
| 品牌方块 2/3/4 列 | 有 Logo 显示 Logo，无 Logo 显示名称 |
| 卡片 1–4 列 | 名称 + 地区 + 右侧小 Logo |
| 截图 1/2/3 列 | 页面截图，整图可点击跳转 |
| 三栏链接列表 | 行优先排列，与原报告阅读顺序一致 |
| 圆角标签 / 表格 | — |
| 世界媒体名录 | 地区 + 目标数 + 三栏媒体清单 |
| 社交分享行 | Facebook / X / LinkedIn / Bluesky |
| 报告摘要面板 | 字数统计、锚文本链接、嵌入图片与图说 |

**配截图**

- 图片拖到任意卡片上（拖多张则依次填充）
- 点中卡片后 `Ctrl+V` 粘贴剪贴板截图
- 批量选图，**按文件名自动匹配条目**（精确 → 模糊 → `01_` 编号 → 顺序补位）

截图存 IndexedDB（localStorage 放不下），导入时压到宽 1400px。

**就地编辑**：右侧预览里的标题、名称、地区直接点击修改。
普通点击 = 编辑，`Ctrl+点击` = 跳转链接。

---

## 导出

| 方式 | 超链接 | 图片 |
|---|---|---|
| 打印 / 另存为 PDF | ✅ 含目录内部跳转锚点 | ✅ |
| 复制到 Google Docs | ✅ | 多数情况 ✅ |
| 下载 `.doc` | ✅ | 多数情况 ✅ |
| 下载 `.html` | ✅ | ✅ |
| Canva 导入 PDF | ❌ Canva 会压掉链接 | ✅ |

Google Docs 不认 CSS grid/flex，所以复制走的是另一套**表格 + 内联样式**的序列化，
版式不会散。

Canva 路线：勾选「附录：链接清单」，再用「导出全部截图为图片文件」拿到原图
（编号与报告顺序一致），在 Canva 里按清单重新挂链接。

---

## 文件说明

```
index.html            主工具（单文件，含全部 CSS/JS）
extract_logos.py      PDF → Logo 图库
build_sample.py       PDF → 完整样例项目
logos.js              生成物：图库（内嵌 PNG）
logos_manifest.json   生成物：名称/域名对照表，可手工订正后重跑重建 logos.js
logos/                生成物：单张 PNG 原图
sample.js             生成物：样例项目
```

生成物均已加入 `.gitignore`：`logos.js` / `logos/` 含第三方媒体 Logo，
`sample.js` 含具体客户的新闻稿内容与配图，都请从你自己的报告现场生成，不随仓库分发。
没有这两个文件时，工具会退回内置的精简示例，其余功能不受影响。

## 环境

浏览器：Chrome / Edge（依赖 IndexedDB、`ClipboardItem`、CSS `columns`）。
脚本：Python 3.9+，`pymupdf`、`pillow`。

## License

MIT
