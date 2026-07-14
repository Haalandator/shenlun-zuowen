#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shuangyao.py —— 钥匙B精确覆盖枚举（共同规范三5配套，cipin.py的姊妹件）

规格（对应规范三5修订版）：
  机器枚举全稿实词在给定材料中的钥匙B精确覆盖，输出覆盖率一行汇总、
  未覆盖词表与近形候疑提示。仅覆盖精确匹配层：近形变体（弱钥匙B）与
  跨词义变形的裁定仍归人工，钥匙A（常用词判断）由语感裁决，本脚本不越权。

实词枚举方式：
  检测到 jieba 时自动启用分词增强——词级枚举（长度≥2的全CJK词，内置停用
  虚词过滤），逐词判材料精确出现，未覆盖词附频次、首现定位与近形候疑提示。
  未安装 jieba 时降级为贪心最长材料片段覆盖（字符口径）——对稿件逐字扫描，
  优先消费材料中精确出现的最长片段（≥2字，窗口上限10字），未被任何材料
  片段覆盖的连续残段（≥2字）列表供人工查漏；此为近似口径，不是分词，
  输出中明示。--no-jieba 可强制走降级路径。

保护词：--protect 传清单文件（每行一词，#起头为注释），命中者免检不入表；
  路标词（首先／其次／再次／最后）内置免检。

用法示例：
  python3 shuangyao.py 稿件.txt 材料.txt
  python3 shuangyao.py 稿件.txt 材料.txt --protect 保护词.txt --top 30
  python3 shuangyao.py 稿件.txt 材料.txt --no-jieba

退出码：0＝枚举完成（未覆盖词以表列示，不改变退出码）；2＝输入错误。
"""

import argparse
import sys

CJK = lambda ch: "\u4e00" <= ch <= "\u9fff"

# 极简停用虚词表（仅为压噪，不承担语法判断）
STOP = set("的了在是和与及或就都也很不之其为以于对把被从等这那此该若并而则乃即如但因故所要有更让")

LUBIAO = ("首先", "其次", "再次", "最后")  # 路标词内置免检（规范三2保护词）

WIN = 10  # 降级路径贪心匹配窗口上限（字）


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        sys.exit(f"错误：无法读取文件——{e}")


def cjk_runs_with_para(raw: str):
    """[(连续CJK片段, 所在段号)]，段＝非空行（与zishu.py默认段落约定一致）。"""
    out = []
    para_no = 0
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        para_no += 1
        cur = []
        for ch in ln:
            if CJK(ch):
                cur.append(ch)
            elif cur:
                out.append(("".join(cur), para_no))
                cur = []
        if cur:
            out.append(("".join(cur), para_no))
    return out


def tokens_by_jieba(text: str):
    import jieba
    toks = []
    for w in jieba.cut(text):
        if len(w) >= 2 and all(CJK(c) for c in w) \
                and not all(c in STOP for c in w):
            toks.append(w)
    return toks


def greedy_cover(runs, cai):
    """降级路径：贪心最长材料片段覆盖。返回(覆盖字符数, 总字符数, 残段列表)。
    残段＝未被材料任何≥2字片段覆盖的连续稿件片段；数学上其任何≥2字子串
    均不在材料中。"""
    covered = 0
    total = 0
    residues = {}   # frag -> [count, first_para]
    singles = 0
    for run, para in runs:
        total += len(run)
        pos = 0
        res = []

        def flush():
            nonlocal singles
            if not res:
                return
            frag = "".join(res)
            res.clear()
            if len(frag) < 2 or all(c in STOP for c in frag):
                singles += 1
                return
            if frag not in residues:
                residues[frag] = [0, para]
            residues[frag][0] += 1

        while pos < len(run):
            best = 0
            for L in range(min(WIN, len(run) - pos), 1, -1):
                if run[pos:pos + L] in cai:
                    best = L
                    break
            if best:
                flush()
                covered += best
                pos += best
            else:
                res.append(run[pos])
                pos += 1
        flush()
    return covered, total, residues, singles


def para_index(raw: str):
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def locate(word: str, paras) -> str:
    for i, p in enumerate(paras, 1):
        if word in p:
            return f"段{i}"
    return "—"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="钥匙B精确覆盖枚举（规范三5配套）。输出覆盖率汇总＋未覆盖词表＋近形候疑提示。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("gaojian", help="稿件文本路径，传 - 读取标准输入")
    ap.add_argument("cailiao", help="给定材料文本路径")
    ap.add_argument("--protect", default=None, help="保护词清单文件（每行一词，#注释），命中免检")
    ap.add_argument("--top", type=int, default=50, help="未覆盖词表最多列示条数（默认50）")
    ap.add_argument("--no-jieba", action="store_true", help="强制降级路径（即使装有jieba）")
    args = ap.parse_args()

    gao = read_text(args.gaojian)
    cai = read_text(args.cailiao)
    if not gao.strip() or not cai.strip():
        sys.exit("错误：稿件或材料为空。")

    protect = set(LUBIAO)
    if args.protect:
        try:
            with open(args.protect, encoding="utf-8") as f:
                for ln in f:
                    w = ln.strip()
                    if w and not w.startswith("#"):
                        protect.add(w)
        except OSError as e:
            sys.exit(f"错误：无法读取保护词清单——{e}")

    use_jieba = False
    if not args.no_jieba:
        try:
            import jieba  # noqa: F401
            use_jieba = True
        except ImportError:
            use_jieba = False

    paras = para_index(gao)

    if use_jieba:
        counts, order = {}, []
        for w in tokens_by_jieba(gao):
            if w in protect:
                continue
            if w not in counts:
                order.append(w)
            counts[w] = counts.get(w, 0) + 1
        total = len(order)
        covered = [w for w in order if w in cai]
        uncovered = [w for w in order if w not in cai]

        # 近形候疑：未覆盖词的≥2字子串在材料中出现 → 提示人工按弱钥匙B裁定（规范三1）
        jinxing = {}
        for w in uncovered:
            hits = set()
            for n in range(len(w) - 1, 1, -1):
                for i in range(len(w) - n + 1):
                    if w[i:i + n] in cai:
                        hits.add(w[i:i + n])
                if hits:
                    break
            if hits:
                jinxing[w] = "、".join(sorted(hits))

        print("〔枚举方式：jieba分词（词级枚举）〕")
        if total:
            print(f"钥匙B精确覆盖汇总｜实词枚举{total}项｜精确覆盖{len(covered)}项｜"
                  f"未覆盖{len(uncovered)}项｜其中近形候疑{len(jinxing)}项｜"
                  f"覆盖率{len(covered) / total * 100:.0f}%")
        else:
            print("钥匙B精确覆盖汇总｜实词枚举0项")
        if uncovered:
            print(f"—— 未覆盖词表（前{min(args.top, len(uncovered))}项，按首现顺序；供钥匙A语感裁决与替换）——")
            for w in uncovered[: args.top]:
                tail = f"｜近形候疑：材料含\"{jinxing[w]}\"，按规范三1弱钥匙B人工裁定" if w in jinxing else ""
                print(f"{w}｜{counts[w]}次｜首现{locate(w, paras)}{tail}")
            if len(uncovered) > args.top:
                print(f"……余{len(uncovered) - args.top}项未列示（--top调大展开）")
        else:
            print("未覆盖词表：空——全部枚举实词均在材料中精确出现。")
    else:
        runs = cjk_runs_with_para(gao)
        covered, total, residues, singles = greedy_cover(runs, cai)
        # 保护词剔除（残段恰为保护词者）
        for w in list(residues):
            if w in protect:
                del residues[w]
        items = sorted(residues.items(), key=lambda kv: gao.find(kv[0]))
        print("〔枚举方式：贪心最长材料片段覆盖（未装jieba或--no-jieba；字符口径近似，仅供查漏，不是分词）〕")
        if total:
            print(f"钥匙B精确覆盖汇总｜稿件CJK共{total}字｜被材料≥2字片段覆盖{covered}字｜"
                  f"覆盖率{covered / total * 100:.0f}%｜未覆盖残段{len(items)}处"
                  f"（另有单字残段{singles}处已忽略，多为虚词）")
        else:
            print("钥匙B精确覆盖汇总｜稿件无CJK字符")
        if items:
            print(f"—— 未覆盖残段表（前{min(args.top, len(items))}处，按首现顺序；其任何≥2字子串均不在材料中，供钥匙A语感裁决与替换）——")
            for frag, (n, para) in items[: args.top]:
                print(f"{frag}｜{n}次｜首现段{para}")
            if len(items) > args.top:
                print(f"……余{len(items) - args.top}处未列示（--top调大展开）")
        else:
            print("未覆盖残段表：空。")
    print("〔边界声明：本脚本仅裁精确匹配层；近形与跨义变形的持钥裁定归人工（规范三1），钥匙A由语感裁决。〕")


if __name__ == "__main__":
    main()
