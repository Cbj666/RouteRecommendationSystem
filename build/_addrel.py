import re, pathlib
p = pathlib.Path(r"projects\runroute_ppt169_20261030\design_spec.md")
t = p.read_text(encoding="utf-8")
rel = {
 1: "kicker → title → subtitle → data band → credits read top to bottom (order); the map is the page field behind the left column (link=field)",
 2: "three numbered facts 01–03 are parallel siblings (order); the quote block is the contrast case for the left column (contrast)",
 3: "Q1 → Q2 → Q3 are parallel questions in reading order (order); the figure band spans all three as shared evidence (membership)",
 4: "table rows are parallel siblings in source→scale→use order (order); the four stat blocks are parallel and read top to bottom (order)",
 5: "采集 → 处理 → 建模 → 服务 is a sequence carried by arrows (order); the footnote line spans the whole pipeline (membership)",
 6: "输入 → 输出 → 解释 is a sequence on the left (order); the prototype screenshot is the shared evidence for all three (link=evidence)",
 7: "four pipeline stages form a sequence (order); the three engineering details are parallel and each pairs a statement with its own proof (link=evidence)",
 8: "six weight rows are parallel siblings (order); the three formulas sit below as the derivation the table refers to (link=derives-from)",
 9: "three conclusions are parallel (order); the distribution block on the right is evidence for the equal-weight conclusion (link=evidence)",
 10: "five steps form a sequence (order); the cost formula defines the weights used by steps three and four (link=defines)",
 11: "three metrics are parallel (order); the two figures below are parallel evidence contrasting a regional variable and a segment variable (contrast)",
 12: "four claims 01–04 are parallel (order); the closing band spans all four as the consequence (membership)",
 13: "one centered phrase followed by one source line (order); none else",
}
def sub(m):
    n = int(m.group(1))
    return m.group(0) + f"- **Relationships**: {rel[n]}\n"
t2 = re.sub(r"#### Slide (\d\d) - [^\n]*\n\n- \*\*Audience move\*\*: [^\n]*\n", sub, t)
p.write_text(t2, encoding="utf-8")
print("inserted", t2.count("**Relationships**"))
