#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cipin.py —— 申论作文流水线高频词组计数核验脚本（共同规范二3配套）

规格（对应规范二3）：
  输入＝给定材料文本＋角色01的提名组表；按规范二3归组口径计数：
  对组内每个词形做精确字符串计数后加总核验，合并后输出前十组，
  标注是否达入表阈值（默认合计≥3次，见角色01第5步）。

去重口径：组内长词形优先计数并遮蔽，防止子串重复计入
  （如"传承性"计入后，其中包含的"传承"不再对同一处重复计数）。
  跨组词形存在包含或重复关系时只输出告警，不自动裁决（按规范一2.1交作者）。

提名组表格式（每行一组，#开头为注释）：
  传承 传承性 传承人
  老手艺：老手艺 老匠人
  词形分隔符可用空格、逗号、顿号；可选"组名：""组名:"前缀，缺省以首个词形为组名。

用法示例：
  python3 cipin.py 材料.txt 提名组表.txt
  python3 cipin.py 材料.txt 提名组表.txt --top 10 --threshold 3

退出码：0＝统计完成；2＝输入错误。
"""

import argparse
import re
import sys

MASK = "\uFFFD"  # 遮蔽占位符，材料文本中不应出现
SPLIT_RE = re.compile(r"[,\uFF0C\u3001\uFF5C|\s]+")  # 逗号/顿号/竖线/空白


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        sys.exit(f"错误：无法读取文件——{e}")


def parse_groups(raw: str):
    """返回 [(组名, [词形…]), …]，组内保持提名顺序、去重。"""
    groups = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = None
        m = re.match(r"^(.+?)[：:]\s*(.+)$", line)
        if m:
            name, rest = m.group(1).strip(), m.group(2)
        else:
            rest = line
        forms, seen = [], set()
        for w in SPLIT_RE.split(rest):
            w = w.strip()
            if not w:
                continue
            if w in seen:
                print(f"⚠组表第{lineno}行：词形“{w}”重复提名，已去重。", file=sys.stderr)
                continue
            seen.add(w)
            forms.append(w)
        if not forms:
            continue
        groups.append((name or forms[0], forms))
    if not groups:
        sys.exit("错误：提名组表为空，无可计数的词形组。")
    return groups


def count_group(text: str, forms):
    """组内长词形优先计数并遮蔽；返回（明细列表[(词形,次数)…], 合计）。"""
    masked = text
    detail = {}
    for form in sorted(forms, key=len, reverse=True):
        n = masked.count(form)  # str.count 本身即非重叠计数
        detail[form] = n
        if n:
            masked = masked.replace(form, MASK * len(form))
    return [(f, detail[f]) for f in forms], sum(detail.values())


def cross_group_warnings(groups):
    warns = []
    flat = [(gname, form) for gname, forms in groups for form in forms]
    for i in range(len(flat)):
        gi, fi = flat[i]
        for j in range(i + 1, len(flat)):
            gj, fj = flat[j]
            if gi == gj:
                continue
            if fi == fj:
                warns.append(f'词形"{fi}"同时提名于组〔{gi}〕与组〔{gj}〕，两组均已计入，存在重复计数')
            elif fi in fj or fj in fi:
                short, long_ = (fi, fj) if len(fi) < len(fj) else (fj, fi)
                warns.append(
                    f'组〔{gi}〕"{fi}"与组〔{gj}〕"{fj}"存在包含关系：'
                    f'"{long_}"的出现处会同时计入"{short}"所在组，存在跨组重复计数'
                )
    return warns


def main() -> None:
    ap = argparse.ArgumentParser(
        description="申论高频词组计数核验（规范二3配套）：组内精确字符串计数加总，输出前十组。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("material", help="给定材料文本路径，传 - 读取标准输入")
    ap.add_argument("groups", help="提名组表路径（角色01提名的归组关系）")
    ap.add_argument("--top", type=int, default=10, help="输出前N组（默认10）")
    ap.add_argument("--threshold", type=int, default=3, help="入表阈值：组合计≥N次（默认3，见角色01第5步）")
    args = ap.parse_args()

    text = read_text(args.material)
    if not text.strip():
        sys.exit("错误：材料文本为空。")
    if MASK in text:
        sys.exit("错误：材料文本含遮蔽占位符\uFFFD（常见于编码损坏），请先按角色01第0步完整性清点处理。")
    groups = parse_groups(read_text(args.groups))

    results = []
    for name, forms in groups:
        detail, total = count_group(text, forms)
        results.append((name, detail, total))
    results.sort(key=lambda r: -r[2])  # 合计降序，同序保持提名顺序（稳定排序）

    print(f"材料字符数（原始，含标点空白）：{len(text)}｜提名组数：{len(groups)}｜入表阈值：合计≥{args.threshold}次")
    print(f"—— 按合计降序，前{min(args.top, len(results))}组 ——")
    for rank, (name, detail, total) in enumerate(results[: args.top], 1):
        parts = "＋".join(f"{f}:{n}" for f, n in detail)
        zeros = [f for f, n in detail if n == 0]
        tag = "入表" if total >= args.threshold else f"未达阈值(<{args.threshold})"
        line = f"第{rank}名｜{name}（{parts}）＝{total}｜{tag}"
        if zeros:
            line += f"｜0次词形：{('、'.join(zeros))}"
        print(line)
    rest = results[args.top:]
    if rest:
        print("其余各组：" + "；".join(f"{name}:{total}" for name, _, total in rest))

    warns = cross_group_warnings(groups)
    if warns:
        print("—— 跨组告警（不自动裁决，按规范一2.1交作者）——")
        for w in warns:
            print("⚠" + w)


if __name__ == "__main__":
    main()
