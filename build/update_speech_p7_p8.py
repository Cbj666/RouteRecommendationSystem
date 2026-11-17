"""把 P7 GIS 段替换为口语版，并补回 P8 六维评价介绍、恢复 P9 cue。

用法：python build/update_speech_p7_p8.py
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.paragraph import Paragraph

DOCX = Path("presentation/G7汇报讲稿-连贯版.docx")
OUT = Path("presentation/G7汇报讲稿-连贯版-P7P8修订.docx")

P7_PARAGRAPHS = [
    "这一页列了六段，但真正要讲的是三步：搭骨架、贴指标、校验落表。归一化和加权是后面的评分部分，这一页先把数据落成一张表。全部用 Python 做，没有 ArcGIS 手工步骤，每一步都能单独重跑。",
    "第一步，搭骨架。我们把 OSM 路网拿过来，只保留能走的 25 类道路，去掉高速；然后投影到 EPSG:32650 的米制坐标——武汉这个纬度，一度经度只有约 96 公里，直接拿经纬度算长度，东西向会偏短；再把路切成一段一段，同一路口只留一个点。最后得到 91,203 段、4.7 万公里的路网。这一步解决的是“路在哪、有多长”。",
    "第二步，把环境信息贴到每一段路上。数据分两类：一类是网格图，像坡度、树冠、空气；一类是点或线，像场馆、路口。坡度、树冠这种沿线变化的，我们沿路段取点，再按长度加权，长路段权重大，避免短路段把平均值带偏；空气分辨率粗，就直接取每一段中点所在的格子。点数据就算每一段到最近场馆的距离，或者数它 200 米内有多少个路口。这样不管原始数据是网格还是点，最后都落到“一段路一个数”。",
    "举两个例子。坡度：把 9 幅 SRTM 30 米高程图拼起来，先做 150 米平滑再求坡——不平滑的话，楼房和树冠会被当成地形。树冠：把 WorldCover 10 米并成 20 米一格，再用 120 米窗口算这段路周围的树荫比例——人感受到的是路段周围的树，不是脚下那一个像素；修好之后，武大 44%、磨山 87%。空气取中点所在的 1 公里网格，只用 NO₂ 进分，PM2.5 全市差异太小，只展示；设施算最近场馆距离；过街数 200 米内路口；安全按道路等级和离主干道的距离扣分。",
    "这一步最花时间的是拼接和取样，我们踩过三个坑。WorldCover 一开始按瓦片偏移贴，后一幅会把前一幅覆盖成 0，武大、磨山的树冠变成 0，远山反而 100%；后来改成按整幅范围一比一合成。SRTM 如果不平滑就差分，城区中位坡度会虚高到 2.66%，最大 533%；所以必须先平滑再求梯度。高德接口有请求频率限制，失败响应不能写进缓存，否则重跑会当成有效结果跳过；后来改成 0.45 秒间隔，失败后等一会儿再重试，间隔越拉越长。",
    "最后，把六类指标落成一张表：segments.gpkg，91,203 行、27 列、44.7 MB；原始数据 12.4 GB，最后就落成这张表。坡度、树冠、空气还有三张中间表，哪一步错了可以单独重跑。到这一步，GIS 的任务就结束了——每条路都有了自己的原始指标。说白了，GIS 不是画地图，而是把环境信息变成每一段路的一列数；后面的六维评分，就是把这些数翻译成 0 到 100 分。",
]

P8_PARAGRAPHS = [
    "这一页讲六维评价。每条路六个子分，每个子分 0 到 100，最后按权重加成一个总分。权重是安全 0.25、绿化 0.25、坡度 0.15、过街 0.10、空气 0.15、设施 0.05；加起来 0.95，所以总分上限是 95，不是 100。这是沿用上一版口径，归一化只改绝对分，不改排序。",
    "六条公式看着多，其实只有三类。第一类查表加阶梯，只有安全：先按道路等级给基础分，人行道 95，主干道 8；离主干道小于 50 米再扣 15 分，小于 20 米再扣 10 分。为什么用阶梯？因为暴露不是线性的，60 米和 500 米差别不大，30 米和 10 米差别很大。",
    "第二类线性，有坡度、过街、空气。坡度 0% 给 100，10% 给 0，10% 是跑步经验上限；过街每 200 米多一个路口扣 7 分，14 个只剩 2 分，15 个才归零，方向是负向，因为跑步怕被打断；空气 NO₂ 10 微克给 100，40 微克给 0，中间线性。这三条都是端点定死，中间按比例。",
    "第三类指数，有绿化和设施。绿化 70% 看树荫，树荫是 0.8 的树冠加 0.2 的绿地占比；树荫越高分越高但会饱和，20% 约 39 分，60% 约 78 分；另外 30% 看 1.5 公里内有没有绿地，越远分越低。设施按到最近场馆的距离衰减，0 米 100 分，500 米约 37 分。为什么用指数？因为树荫和设施都是够用就好，不是越多越线性。",
    "这六维不是拍脑袋分的，指标分层参考了步行环境研究里的功能、安全、美观、目的地四类要素，再落到跑步场景。公式也不是拟合出来的：我们没有人工标注，也没有真实轨迹，做不了监督学习。做法是三步：先定函数族，要单调、有界、端点能解释；再定端点；最后选最简单的形式。这里要说明，只有空气的 10 和 40 是公开标准，10 是 WHO 2021 年均指导值，40 是 GB 3095—2012 二级年均；坡度 10%、绿化 1500 米、设施 500 米、安全查表和 50/20 米，都是工程锚点，不是国标。绿化和安全还是代理指标：绿化用卫星树冠，不是街景绿视率，和街景相关只有 0.617；安全没有逐段流量，只能用道路等级和离主干道距离代理。",
    "最后，六个子分按权重加起来就是 score，再按 40、55、70、85 分五档，分成差、一般、较好、好、很好。权重为什么是这几个数，下一页讲。",
]

P9_CUE = "【P9 · 调参与敏感性检验｜指权重检验】"


def find_paragraph(doc: Document, needle: str) -> Paragraph:
    for paragraph in doc.paragraphs:
        if needle in paragraph.text:
            return paragraph
    raise LookupError(f"找不到段落：{needle}")


def body_between(doc: Document, start: Paragraph, end: Paragraph) -> list[Paragraph]:
    result = []
    element = start._p.getnext()
    while element is not None and element is not end._p:
        result.append(Paragraph(element, start._parent))
        element = element.getnext()
    return result


def style_body(paragraph: Paragraph) -> None:
    paragraph.style = "SpeechBody"
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def style_cue(paragraph: Paragraph) -> None:
    paragraph.style = "SpeechCue"


def main() -> None:
    doc = Document(str(DOCX))
    p7_cue = find_paragraph(doc, "【P7 · GIS")
    p8_cue = find_paragraph(doc, "【P8 · 六维")
    p10_cue = find_paragraph(doc, "【P10 ·")

    p7_body = body_between(doc, p7_cue, p8_cue)
    if not p7_body:
        raise RuntimeError("P7 段没有找到正文")

    anchor = p7_body[0]
    for text in P7_PARAGRAPHS:
        new_paragraph = anchor.insert_paragraph_before(text)
        style_body(new_paragraph)
    for paragraph in p7_body:
        paragraph._element.getparent().remove(paragraph._element)

    p8_body = body_between(doc, p8_cue, p10_cue)
    if not p8_body:
        raise RuntimeError("P8 段没有找到正文")
    sensitivity_paragraph = p8_body[0]
    for text in P8_PARAGRAPHS:
        new_paragraph = sensitivity_paragraph.insert_paragraph_before(text)
        style_body(new_paragraph)
    new_cue = sensitivity_paragraph.insert_paragraph_before(P9_CUE)
    style_cue(new_cue)
    new_cue.paragraph_format.keep_with_next = True

    for paragraph in doc.paragraphs:
        if paragraph.style.name == "SpeechCue":
            paragraph.paragraph_format.keep_with_next = True
        elif paragraph.style.name == "SpeechBody":
            paragraph.paragraph_format.keep_together = True

    doc.save(str(OUT))
    print(f"saved: {OUT}")
    print(f"paragraphs: {len(doc.paragraphs)}")


if __name__ == "__main__":
    main()
