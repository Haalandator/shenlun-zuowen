#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zishu.py —— 申论作文流水线字数统计脚本（共同规范二3配套）

规格（对应规范二3）：
  参数化"标点计入／标题计入／空格不计"口径与字数上下限，
  输出"逐段字数＋合计＋余量"一行交接单格式。
  默认口径＝规范二3默认值：标点计入、单独成行的标题计入、空格不计。

段落约定：每个非空行视为一个自然段；默认首个非空行视为单独成行的标题
（无标题时传 --biaoti wu）。
--join-wrapped（角色05成稿预处理配套，规范二3.1）改用段界推导：段界＝空行
或行首全角空格缩进；段内硬换行合并（每行去首尾空白后无缝拼接）；--biaoti
非 wu 时首个非空行独立为标题段。未检测到任何段界时并为单段并告警。

用法示例：
  python3 zishu.py 稿件.txt --min 1000 --max 1200
  python3 zishu.py 成稿.txt --join-wrapped --min 1000 --max 1200   # OCR硬换行成稿
  python3 zishu.py 稿件.txt --min 1000 --max 1200 --budget "180,300,300,300,220"
  cat 稿件.txt | python3 zishu.py - --biaoti wu --biaodian buji
  python3 zishu.py 稿件.txt --detail        # 附逐段明细表（一行交接单照常输出）

退出码：0＝统计完成（越界与偏离以⚠行提示，不改变退出码）；2＝输入错误。
"""

import argparse
import sys
import unicodedata


def count_chars(text: str, count_punct: bool, count_space: bool) -> int:
    """按口径统计单段字符数。换行符一律不计。"""
    total = 0
    for ch in text:
        if ch in "\r\n":
            continue
        if ch.isspace():  # 含半角空格、Tab、全角空格\u3000
            if count_space:
                total += 1
            continue
        if unicodedata.category(ch).startswith("P"):  # 全半角标点均归P类
            if count_punct:
                total += 1
            continue
        total += 1
    return total


def split_paragraphs(raw: str, join_wrapped: bool, has_title: bool):
    """段落推导。join_wrapped=False：每个非空行一段（原行为）。
    join_wrapped=True：段界＝空行或行首全角空格缩进；段内各行去首尾空白后
    无缝拼接；has_title 时首个非空行独立为标题段。返回 (段列表, 告警或None)。"""
    if not join_wrapped:
        return [ln for ln in raw.splitlines() if ln.strip()], None
    lines = raw.splitlines()
    paras, cur = [], []

    def close():
        if cur:
            paras.append("".join(cur))
            cur.clear()

    seen_nonblank = False
    boundary = False
    for ln in lines:
        s = ln.strip()
        if not s:
            if seen_nonblank:
                boundary = True
            close()
            continue
        if ln.startswith("\u3000"):
            if seen_nonblank:
                boundary = True
            close()
        if has_title and not seen_nonblank:
            seen_nonblank = True
            paras.append(s)  # 标题独立成段，不与正文首段合并
            continue
        seen_nonblank = True
        cur.append(s)
    close()

    warn = None
    n_nonblank = sum(1 for l in lines if l.strip())
    n_body = len(paras) - (1 if has_title and paras else 0)
    if not boundary and n_body <= 1 and n_nonblank > (2 if has_title else 1):
        warn = "⚠--join-wrapped：未检测到段界（空行或行首全角缩进），正文已并为单段，请人工核对分段。"
    return paras, warn


def parse_budget(raw: str, n_body: int):
    parts = [p for p in raw.replace("，", ",").split(",") if p.strip()]
    try:
        budget = [int(p) for p in parts]
    except ValueError:
        sys.exit("错误：--budget 须为逗号分隔的整数（正文逐段预算，不含标题）。")
    if len(budget) != n_body:
        print(
            f"⚠预算核对：预算段数{len(budget)}与正文段数{n_body}不一致，"
            f"仅按前{min(len(budget), n_body)}段比对。",
            file=sys.stderr,
        )
    return budget


def main() -> None:
    ap = argparse.ArgumentParser(
        description="申论字数统计（规范二3配套）。输出一行交接单格式：逐段字数＋合计＋余量。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("file", help="稿件文本路径，传 - 读取标准输入")
    ap.add_argument("--min", type=int, default=None, help="题目字数下限")
    ap.add_argument("--max", type=int, default=None, help="题目字数上限")
    ap.add_argument(
        "--biaodian", choices=["ji", "buji"], default="ji",
        help="标点口径：ji=计入（默认，对齐答题卡按格计）／buji=不计",
    )
    ap.add_argument(
        "--biaoti", choices=["ji", "buji", "wu"], default="ji",
        help="标题口径：ji=首个非空行为标题且计入合计（默认）／buji=为标题但不计入合计／wu=文本无标题",
    )
    ap.add_argument(
        "--kongge", choices=["ji", "buji"], default="buji",
        help="空格口径：buji=不计（默认）／ji=计入",
    )
    ap.add_argument(
        "--budget", default=None,
        help='提纲逐段预算（正文，不含标题），如 "180,300,300,300,220"；偏离超20%%自动标记（规范二3）',
    )
    ap.add_argument(
        "--join-wrapped", action="store_true",
        help="成稿预处理（角色05配套，规范二3.1）：合并段内硬换行，段界＝空行或行首全角空格缩进；--biaoti非wu时首个非空行独立为标题段",
    )
    ap.add_argument("--detail", action="store_true", help="在一行交接单之后附逐段明细表")
    args = ap.parse_args()

    if args.file == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(args.file, encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            sys.exit(f"错误：无法读取文件——{e}")

    paragraphs, jw_warn = split_paragraphs(raw, args.join_wrapped, args.biaoti != "wu")
    if not paragraphs:
        sys.exit("错误：输入为空，无可统计段落。")
    if jw_warn:
        print(jw_warn)

    count_punct = args.biaodian == "ji"
    count_space = args.kongge == "ji"

    title_text = None
    if args.biaoti != "wu":
        title_text = paragraphs[0]
        body = paragraphs[1:]
    else:
        body = paragraphs

    title_n = count_chars(title_text, count_punct, count_space) if title_text is not None else 0
    body_counts = [count_chars(p, count_punct, count_space) for p in body]
    body_total = sum(body_counts)
    total = body_total + (title_n if args.biaoti == "ji" else 0)

    # —— 组装一行交接单 ——
    koujing = "·".join([
        "标点计入" if count_punct else "标点不计",
        {"ji": "标题计入", "buji": "标题不计", "wu": "无标题"}[args.biaoti],
        "空格计入" if count_space else "空格不计",
    ])
    cells = [f"〔口径：{koujing}〕"]
    if title_text is not None:
        cells.append(f"标题{title_n}")
    cells += [f"段{i}:{n}" for i, n in enumerate(body_counts, 1)]
    if title_text is not None and args.biaoti == "ji":
        cells.append(f"合计{total}（标题{title_n}＋正文{body_total}，正文{len(body)}段）")
    else:
        cells.append(f"合计{total}（正文{len(body)}段）")

    warns = []
    if args.min is not None or args.max is not None:
        lo = args.min if args.min is not None else "—"
        hi = args.max if args.max is not None else "—"
        parts = []
        if args.min is not None:
            d = total - args.min
            parts.append(f"距下限{d:+d}")
            if d < 0:
                warns.append(f"⚠合计低于下限{-d}字")
        if args.max is not None:
            d = args.max - total
            parts.append(f"距上限{d:+d}")
            if d < 0:
                warns.append(f"⚠合计超出上限{-d}字")
        cells.append(f"限{lo}–{hi}")
        cells.append("余量：" + "／".join(parts))
    else:
        cells.append("未设上下限")

    print("｜".join(cells))

    # —— 预算偏离核对（规范二3：逐段偏离提纲预算超过20%须说明原因）——
    if args.budget:
        budget = parse_budget(args.budget, len(body_counts))
        devs = []
        for i, (n, b) in enumerate(zip(body_counts, budget), 1):
            if b <= 0:
                continue
            pct = (n - b) / b * 100
            if abs(pct) > 20:
                devs.append(f"段{i}偏离{pct:+.0f}%（实{n}／预算{b}）")
        if devs:
            print("⚠预算核对：" + "；".join(devs) + "——须说明原因（规范二3）")
        else:
            print("预算核对：逐段偏离均≤20%")

    for w in warns:
        print(w)

    if args.detail:
        print("—— 逐段明细 ——")
        if title_text is not None:
            mark = "（计入）" if args.biaoti == "ji" else "（不计入合计）"
            print(f"标题｜{title_n}字{mark}｜{title_text[:20]}{'…' if len(title_text) > 20 else ''}")
        for i, (p, n) in enumerate(zip(body, body_counts), 1):
            print(f"段{i}｜{n}字｜{p[:20]}{'…' if len(p) > 20 else ''}")


if __name__ == "__main__":
    main()
