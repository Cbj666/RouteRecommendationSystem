from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.dml import MSO_THEME_COLOR
from PIL import Image

ROOT = Path(__file__).resolve().parent
AS = ROOT / '素材'
OUT = ROOT / '项目展示-runroute-20261030_updated.pptx'
W, H = 13.333, 7.5
BG='FFFFFF'; INK='153B2F'; GREEN='15503C'; MID='7FA894'; PALE='E7F0EA'; MINT='C9DED1'; ORANGE='D95E36'; TEXT='1D2A25'; MUTED='62736A'; SOFT='F4F7F4'; LINE='D6E1D9'
FONT='Microsoft YaHei'; FONT2='DengXian'
prs=Presentation(); prs.slide_width=Inches(W); prs.slide_height=Inches(H)
prs.core_properties.title='城市慢跑 / 慢骑环境适宜性评价与路线推荐'; prs.core_properties.subject='以武汉为例 · 重构版课程项目展示'; prs.core_properties.author='汇报小组 G7'
blank=prs.slide_layouts[6]

def rgb(h): return RGBColor.from_string(h)
def shape(slide, typ, x,y,w,h, fill=None, line=None, trans=0):
    s=slide.shapes.add_shape(typ, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb=rgb(fill or BG); s.fill.transparency=trans
    if line:
        s.line.color.rgb=rgb(line); s.line.width=Pt(1)
    else: s.line.fill.background()
    return s
def rect(slide,x,y,w,h,c): return shape(slide,MSO_SHAPE.RECTANGLE,x,y,w,h,c)
def line(slide,x,y,w,h,c=LINE,pt=1):
    s=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x+w), Inches(y+h)); s.line.color.rgb=rgb(c); s.line.width=Pt(pt); return s
def txt(slide,text,x,y,w,h,size=18,color=TEXT,bold=False,font=FONT,align=PP_ALIGN.LEFT,valign=MSO_ANCHOR.TOP,margin=0,rot=0):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); box.rotation=rot
    tf=box.text_frame; tf.clear(); tf.word_wrap=True; tf.margin_left=tf.margin_right=Inches(margin); tf.margin_top=tf.margin_bottom=Inches(margin); tf.vertical_anchor=valign
    for j, st in enumerate(str(text).split('\n')):
        p=tf.paragraphs[0] if j==0 else tf.add_paragraph(); p.alignment=align; p.space_before=Pt(0); p.space_after=Pt(0)
        r=p.add_run(); r.text=st; r.font.name=font; r.font.size=Pt(size); r.font.bold=bold; r.font.color.rgb=rgb(color)
    return box
def img(slide,name,x,y,w,h=None,contain=True):
    p=AS/name
    with Image.open(p) as im: iw,ih=im.size
    if h is None: h=w*ih/iw
    if contain:
        sc=min(w/iw,h/ih); ww=iw*sc; hh=ih*sc; xx=x+(w-ww)/2; yy=y+(h-hh)/2
        return slide.shapes.add_picture(str(p), Inches(xx), Inches(yy), width=Inches(ww), height=Inches(hh))
    return slide.shapes.add_picture(str(p), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
def base(kicker,title,num,subtitle=None,dark=False):
    s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=rgb(INK if dark else BG)
    fg=BG if dark else INK; muted=MINT if dark else MUTED
    txt(s,kicker.upper(),.62,.35,10,.28,10,muted,True,FONT2)
    txt(s,title,.62,.78,12.0,.72,30,fg,True)
    if subtitle: txt(s,subtitle,.65,1.52,11.9,.35,13,muted,False)
    txt(s,f'{num:02d} / 12',11.85,7.08,.9,.2,9,muted,True,FONT2,PP_ALIGN.RIGHT)
    return s
def note(s, body): s.notes_slide.notes_text_frame.text=body
def arrow(s,x1,y1,x2,y2,c=GREEN,pt=1.5):
    sh=s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)); sh.line.color.rgb=rgb(c); sh.line.width=Pt(pt); sh.line.end_arrowhead=True; return sh

# 1 cover
s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=rgb(INK)
rect(s,0,0,.18,H,ORANGE); img(s,'A1_行政区_全市.png',7.05,.05,5.7,7.25)
shape(s,MSO_SHAPE.PARALLELOGRAM,7.2,.1,5.35,7.15,GREEN,None,30)
txt(s,'城市空间分析 · 课程项目展示',.72,.72,5.8,.28,12,MINT,True)
txt(s,'让每一段路\n都值得跑',.72,1.45,6.4,1.9,39,BG,True)
rect(s,.72,3.75,.76,.09,ORANGE); txt(s,'慢跑 / 慢骑环境适宜性评价\n与路线推荐',.72,4.05,6.3,.9,21,MINT,True)
txt(s,'以武汉为例',.74,5.35,4,.35,15,BG,False)
txt(s,'91,203 段路网     47,051 km     六维评价',.74,6.46,6,.3,13,BG,True,FONT2)
txt(s,'汇报小组 G7  ·  2026.11',.74,7.02,4,.2,9,MINT,False)
note(s,'各位老师、同学好，我们这组的题目是《城市慢跑 / 慢骑环境适宜性评价与路线推荐》，落点在武汉。一句话说清楚我们做了什么：给每一条路计算适宜性分，再把路段分数转成闭合环线的路径代价。下面按问题、数据、方法、检验和结论展开。')

# 2 framing
s=base('01 · 问题意识','同样 5 公里，环境体验并不相同',2,'把“该走哪里”从经验问题，变成可计算、可解释的问题')
img(s,'B1_路网_中心城.png',.58,2.12,7.35,4.65)
# visual emphasized route contrast
shape(s,MSO_SHAPE.PARALLELOGRAM,8.1,2.28,4.42,3.95,PALE)
txt(s,'路线距离相同',8.55,2.72,3.5,.36,16,MUTED,True)
txt(s,'环境条件不同',8.52,3.24,3.9,.74,30,INK,True)
rect(s,8.55,4.32,.13,.64,ORANGE); txt(s,'坡度 · 遮阴 · 过街\n机动车暴露 · 补给',8.88,4.27,3.4,.92,16,TEXT,True)
txt(s,'路线图不应只告诉我们“怎么走”',8.55,5.65,3.8,.5,14,GREEN,True)
note(s,'同样是5公里，沿江滩跑和沿主干道跑，噪声、尾气、坡度、人车冲突完全不同。但地图上两段路看起来一样。绿道在增加，信息却散落在推文、评论和本地人的记忆里。项目希望让“这条路适不适合跑”变成可以计算、可以解释的事情。')

# 3 scale
s=base('02 · 系统产出','把 9.1 万段路，变成可读的城市底图',3,'离线数据管线 + 路段评分 + 路线生成；当前交付为计算成果与静态原型')
img(s,'A2_路网_全市.png',7.55,1.92,4.9,4.9)
for x,num,label,sub in [(0.82,'91,203','评分路段','逐段赋值'),(3.05,'47,051','公里路网','投影计算长度'),(5.2,'6','评价维度','可回溯指标')]:
    txt(s,num,x,2.38,2.0,.73,37,GREEN,True,FONT2); txt(s,label,x,3.28,2.05,.36,15,INK,True); txt(s,sub,x,3.72,2,.25,11,MUTED)
line(s,.82,4.55,5.95,0,LINE,1)
txt(s,'14.9–81.4',.82,4.91,2.6,.58,27,ORANGE,True,FONT2); txt(s,'路段综合分范围',.82,5.61,3,.32,13,MUTED)
txt(s,'54.0',4.38,4.91,1.65,.58,27,INK,True,FONT2); txt(s,'评分中位数',4.38,5.61,2,.32,13,MUTED)
txt(s,'分数用于比较路段环境适宜性，不是人体生理测量。',.82,6.45,6.1,.28,11,MUTED)
note(s,'全市参与评分的道路为91,203段，投影后的总长度47,051.2公里。综合分中位数54分，10到90分位为39.7到64.1。评分是道路环境适宜性的模型代理，不等同于人体主观体验或实测生理负荷。当前主要交付是离线计算管线、评分数据和静态高保真原型，线上服务化仍是后续工作。')

# 4 data pipeline
s=base('03 · 数据链路','五类数据，落到同一条路段记录',4,'统一空间基准后提取指标；距离与坡度在 EPSG:32650 中计算')
# simple left-to-right pipeline, diagonals
steps=[('01','OSM','路网结构'),('02','SRTM','坡度'),('03','WorldCover','树冠 / 绿地'),('04','POI','设施邻近'),('05','CHAP','1 km 空气网格')]
for i,(n,head,sub) in enumerate(steps):
    x=.72+i*2.5
    shape(s,MSO_SHAPE.PARALLELOGRAM,x,2.24,2.08,1.06,PALE if i%2==0 else SOFT)
    txt(s,n,x+.16,2.37,.45,.22,10,ORANGE,True,FONT2); txt(s,head,x+.16,2.7,1.8,.32,15,INK,True); txt(s,sub,x+.16,3.5,1.9,.28,11,MUTED)
    if i<4: arrow(s,x+2.08,2.76,x+2.43,2.76,GREEN,1.2)
rect(s,.72,4.45,11.8,.02,LINE)
txt(s,'12 GB',.78,4.85,2.5,.7,37,INK,True,FONT2); txt(s,'原始资料，本地保留',.8,5.53,3.5,.27,12,MUTED)
arrow(s,4.2,5.2,6.05,5.2,ORANGE,2)
txt(s,'可复跑脚本',6.32,4.89,2.3,.48,22,GREEN,True); txt(s,'采集 → 对齐 → 指标 → 评分',6.32,5.54,4.2,.32,14,MUTED)
txt(s,'空气：1 km 年均 NO₂ 网格，只刻画区域差异；相邻道路之间不具备实测级分辨率。',.78,6.42,11.7,.36,12,ORANGE,True)
note(s,'数据来源包括OSM路网、SRTM地形、ESA WorldCover、高德运动场馆和CHAP再分析空气网格。全部采用WGS84存储，但长度和坡度先投影到EPSG:32650再计算。空气是1公里网格匹配到路段附近，用作区域校正，不是逐路实测。原始数据本地保留，脚本可以重跑派生结果。')

# 5 model
s=base('04 · 评价模型','六个维度，六种可解释的“跑步条件”',5,'先把每维统一到 0–100，再按固定权重加总；当前权重合计 0.95')
items=[('安全','0.25','道路等级 / 主干道距离'),('绿化','0.25','树冠覆盖 / 绿地邻近'),('坡度','0.20','SRTM 平滑坡度'),('过街','0.10','200 m 路口密度'),('空气','0.10','NO₂ 区域校正'),('设施','0.05','运动设施步行距离')]
for i,(a,w,d) in enumerate(items):
    y=2.05+i*.68
    txt(s,a,.88,y,1.0,.32,15,INK,True); txt(s,w,2.08,y,1.0,.32,15,GREEN,True,FONT2)
    shape(s,MSO_SHAPE.RECTANGLE,3.12,y+.08,3.45,.18,SOFT); shape(s,MSO_SHAPE.RECTANGLE,3.12,y+.08,3.45*float(w)/.25,.18,GREEN if i<2 else MID)
    txt(s,d,6.85,y,3.6,.32,12,MUTED)
    if i<5: line(s,.86,y+.52,9.9,0,LINE,.55)
shape(s,MSO_SHAPE.PARALLELOGRAM,10.65,2.02,1.95,3.95,INK)
txt(s,'TOTAL',10.98,2.43,1.25,.28,10,MINT,True,FONT2,PP_ALIGN.CENTER)
txt(s,'0.95',10.78,3.02,1.65,.68,31,BG,True,FONT2,PP_ALIGN.CENTER)
txt(s,'保留历史\n评分尺度',10.93,4.03,1.35,.8,13,BG,True,align=PP_ALIGN.CENTER)
txt(s,'设施子分中位数仅 3.0：低区分度是模型已知边界。',.88,6.45,9.6,.32,12,ORANGE,True)
note(s,'六维包括安全、绿化、坡度、过街、空气和设施。各维归一化到0到100，再按显式权重加权。正式评分的权重合计0.95，是为了沿用原评分尺度，不强行归一到1。设施子分中位数只有3分，说明该维度在当前数据覆盖下区分度有限。树冠覆盖不是街景绿视率；安全也没有真实路段流量，因此指标属于可解释代理。')

# 6 map
s=base('05 · 空间表达','把抽象分数放回真实街道',6,'全市路网呈现骨架；中心城路线用于检视算法输出')
img(s,'F2_热力六边形_带边界.png',.74,2.0,4.6,4.62)
img(s,'B2_路线_环线5km.png',5.58,2.12,3.15,3.9)
img(s,'C2_路线_单行线10km_紧裁.png',8.95,2.12,1.58,3.9)
img(s,'C3_路线_马拉松42km_紧裁.png',10.62,2.3,2.0,3.4)
txt(s,'IDW 插值 · 非实测',1.55,5.95,2.8,.32,12,ORANGE,True,align=PP_ALIGN.CENTER)
txt(s,'环线 5 km',5.92,6.2,2.5,.3,12,INK,True,align=PP_ALIGN.CENTER)
txt(s,'单向 10 km',8.68,6.2,2.1,.3,12,INK,True,align=PP_ALIGN.CENTER)
txt(s,'马拉松',10.6,6.2,2.0,.3,12,INK,True,align=PP_ALIGN.CENTER)
txt(s,'左：55 个起点的空间插值；右：三类路线的紧裁形态对比。',.78,6.68,11.5,.25,10,MUTED)
note(s,'左图的六边形热力来自55个样点的前三条5公里环线均分，经IDW插值得到，只在距离样点9公里内呈现。它是空间插值，不是实测连续面；越远离样本点不确定性越高。右图展示同一中心城范围内三种演示路线，路线类别和透明度不同，便于比较空间形态。')

# 7 validation
s=base('06 · 稳健性检验','小幅调整权重，整体排序几乎不变',7,'16 组方案：单维 ±20% 扰动 + 4 组整套权重替换；Spearman 衡量排序一致性')
# big range
rect(s,.78,2.02,7.85,3.52,SOFT)
txt(s,'单维扰动',1.12,2.38,2.2,.34,14,MUTED,True)
txt(s,'0.9940',1.08,2.88,3.0,.74,34,GREEN,True,FONT2)
txt(s,'—',4.12,3.08,.5,.3,20,MUTED,True,align=PP_ALIGN.CENTER)
txt(s,'0.9995',5.05,2.88,3.0,.74,34,GREEN,True,FONT2)
txt(s,'Spearman 相关系数范围',1.13,3.85,4.4,.34,14,INK,True)
line(s,1.15,4.58,6.95,0,MID,3); shape(s,MSO_SHAPE.OVAL,1.04,4.44,.26,.26,ORANGE); shape(s,MSO_SHAPE.OVAL,7.93,4.44,.26,.26,GREEN)
txt(s,'秩序稳定',1.13,4.93,2.4,.31,13,GREEN,True)
shape(s,MSO_SHAPE.PARALLELOGRAM,9.06,2.02,3.46,3.52,INK)
txt(s,'整套权重改变',9.43,2.38,2.6,.34,13,MINT,True)
txt(s,'0.8887',9.38,2.98,2.5,.67,31,BG,True,FONT2)
txt(s,'全部等权',9.45,3.78,2.4,.3,14,BG,True)
txt(s,'整体结构会重排',9.45,4.45,2.5,.34,12,MINT)
txt(s,'Top 10% 重合率最低 92.65%（单维扰动）；等权方案 62.59%。',.87,6.25,11.7,.34,12,ORANGE,True)
note(s,'敏感性分析覆盖16组方案。单独把某一维权重上下调整20%，排序Spearman在0.9940到0.9995之间，top10%重合率最低92.65%。全部等权时Spearman下降到0.8887，top10%重合率62.59%。因此小幅调整稳健，但若改变整套权重结构，结果会明显重排。设施维度低区分度需要优先改进，不应只追求调权。')

# 8 route algo
s=base('07 · 路线算法','把“高分路段”转成较低的通行代价',8,'偏好子分控制路段代价；环线由去程 + 反向惩罚后的回程组成')
# equation
shape(s,MSO_SHAPE.PARALLELOGRAM,.78,2.1,11.75,1.25,PALE)
txt(s,'边代价',1.12,2.46,1.2,.36,15,MUTED,True)
txt(s,'长度 × (1 + (100 − 偏好子分) / 40)',2.62,2.35,8.9,.56,25,INK,True,FONT2,PP_ALIGN.CENTER)
# directional chain
steps=[('01','选折点','约半程距离带'),('02','去程寻路','偏好代价最短路'),('03','双向惩罚','去程边回程 ×4'),('04','回程闭合','Dijkstra 再寻路')]
for i,(n,h,b) in enumerate(steps):
    x=.86+i*3.13
    shape(s,MSO_SHAPE.PARALLELOGRAM,x,4.14,2.55,1.2,SOFT if i%2==0 else PALE)
    txt(s,n,x+.17,4.3,.48,.25,10,ORANGE,True,FONT2); txt(s,h,x+.17,4.68,2.17,.31,15,INK,True); txt(s,b,x+.17,5.57,2.3,.3,11,MUTED)
    if i<3: arrow(s,x+2.57,4.75,x+3.04,4.75,GREEN,1.4)
txt(s,'低分路段代价最高约 3.5×    ·    回程边双向 ×4，降低原路折返',.92,6.48,11.6,.3,13,GREEN,True)
note(s,'对每一条道路，把长度乘以一个由偏好子分决定的加价系数。低分路段可贵到3.5倍。环线先在目标距离约一半的位置选折点，去程用Dijkstra；回程将去程走过的边双向乘以4后，再求最短路。双向惩罚很关键，否则反向走回去不会被惩罚。候选路线还需通过目标里程范围筛选。')

# 9 case
s=base('08 · 路线案例','一张路网，三种不同的路线任务',9,'同一武大起点的演示路线；分数是偏好匹配分，不等同路段六维综合分')
img(s,'C1_路线_环线5km_紧裁.png',.78,2.0,5.3,4.5)
shape(s,MSO_SHAPE.PARALLELOGRAM,6.35,2.05,6.1,4.55,PALE)
txt(s,'5 km',6.78,2.4,1.5,.55,28,INK,True,FONT2)
txt(s,'环线',8.28,2.53,1.2,.32,14,GREEN,True)
txt(s,'78.5',10.38,2.4,1.5,.55,27,ORANGE,True,FONT2,PP_ALIGN.RIGHT)
line(s,6.76,3.22,5.05,0,'B7CBBE',.9)
txt(s,'实际 5.34 km  ·  32 分钟',6.78,3.42,4.9,.35,15,INK,True)
txt(s,'预估指标：树冠 58%  ·  平均坡度 3.5%  ·  最近场馆 240 m',6.78,4.06,5.0,.62,12,MUTED)
txt(s,'六维子分：安全 84  /  绿化与滨水 81  /  坡度平缓 65',6.78,4.95,5.05,.56,12,GREEN,True)
txt(s,'演示扩展',6.78,5.85,1.7,.28,11,ORANGE,True)
txt(s,'10 km 单向  ·  42 km 马拉松（目标 42.195 km）',8.33,5.85,4.0,.42,11,INK)
txt(s,'目标里程与实际长度略有差异；不同路线的偏好分不宜直接当作路段综合分比较。',.82,6.72,11.6,.24,10,MUTED)
note(s,'以武大附近为同一演示起点，环线目标5公里，实际5.34公里，偏好匹配分78.5；单向路线目标10公里，实际10.35公里，分74.6；马拉松演示目标42.195公里，实际41.72公里，分63.5。这里的路线分是按照路线偏好计算，不是六维评分表中路段综合分，三类路线也属于演示扩展，不代表都已接入统一线上服务。')

# 10 air limits
s=base('09 · 可信边界','空气数据适合做区域校正，不适合逐路排名',10,'空间网格约 1 km；同圈层内道路之间的 NO₂ 差异不足以支持精细比较')
# concentric / scale graphic
shape(s,MSO_SHAPE.OVAL,1.0,2.15,4.05,4.05,PALE)
shape(s,MSO_SHAPE.OVAL,1.55,2.7,2.95,2.95,MINT)
shape(s,MSO_SHAPE.OVAL,2.1,3.25,1.85,1.85,GREEN)
txt(s,'中心城区',2.46,3.83,1.16,.32,13,BG,True,align=PP_ALIGN.CENTER)
txt(s,'1 km 网格',2.22,5.24,1.65,.28,11,INK,True,align=PP_ALIGN.CENTER)
txt(s,'NO₂ 区域差异',1.72,6.38,2.6,.28,12,MUTED,True,align=PP_ALIGN.CENTER)
txt(s,'28.8',6.18,2.44,2.0,.58,30,INK,True,FONT2); txt(s,'→',8.12,2.48,.55,.44,21,ORANGE,True,align=PP_ALIGN.CENTER); txt(s,'18.9',9.02,2.44,2.0,.58,30,GREEN,True,FONT2)
txt(s,'城区到外围年均 NO₂（µg/m³）',6.2,3.12,5.2,.3,13,MUTED)
line(s,6.18,3.75,5.2,0,LINE,1)
txt(s,'0.2–1.8',6.18,4.2,2.3,.58,26,ORANGE,True,FONT2); txt(s,'µg/m³',6.25,4.86,2,.27,12,MUTED)
txt(s,'同圈层不同道路的 NO₂ 差异',8.12,4.34,3.4,.6,15,INK,True)
txt(s,'不用于逐段区分',8.12,5.18,3.5,.36,14,ORANGE,True)
txt(s,'评分中的空气维度使用 NO₂ 年均网格；月度 PM₂.₅ 仅用于补充展示。',6.19,6.38,6.2,.34,11,MUTED)
note(s,'空气数据来自CHAP约1公里年均网格，区域差异可表达为中心城区到外围NO2年均约28.8降至18.9微克每立方米。但同一圈层不同道路的差异仅0.2到1.8微克每立方米，不足以支持逐路排名，所以模型将空气作为区域校正。月度PM2.5可以展示季节变化，但它不直接进入当前路段评分。')

# 11 conclusions
s=base('10 · 结论与局限','模型能回答“怎么比”，不能替代“实地体验”',11,'把结果用作路线筛选与讨论起点，而不是绝对的“最佳路线”结论')
# diagonal conclusion band
shape(s,MSO_SHAPE.PARALLELOGRAM,.82,2.1,7.28,1.15,INK)
txt(s,'可解释评分  +  偏好寻路  +  环线闭合',1.14,2.44,6.4,.42,21,BG,True,align=PP_ALIGN.CENTER)
for i,(n,h,b) in enumerate([('01','可复现','数据和脚本形成离线流水线'),('02','可解释','每维有来源、变换与权重'),('03','可迭代','后续补街景、流量与设施供给')]):
    y=3.72+i*.78; txt(s,n,.98,y,.48,.28,10,ORANGE,True,FONT2); txt(s,h,1.62,y,1.5,.32,15,GREEN,True); txt(s,b,3.35,y,5.0,.32,13,TEXT)
# right bounds
rect(s,9.05,2.08,3.47,4.7,SOFT)
txt(s,'已知边界',9.42,2.4,2.5,.34,17,INK,True)
for i,t in enumerate(['安全以道路等级代理，无车流量','卫星树冠 ≠ 街景绿视率','设施 POI 覆盖存在空间差异','空气网格不区分相邻道路']):
    y=3.12+i*.77; rect(s,9.43,y+.08,.12,.12,ORANGE); txt(s,t,9.72,y,2.35,.56,12,TEXT)
txt(s,'下一步：补充观测数据，再评估模型偏差。',.98,6.57,7.4,.3,13,ORANGE,True)
note(s,'我们得到的是一个可以复现、解释和迭代的评价与寻路框架，不是绝对客观的最佳路线判定器。安全通过道路等级代理，没有实际车流量；绿化使用卫星树冠，不是街景绿视率；设施POI覆盖有差异；空气网格无法区分相邻道路。下一步应补充街景、交通流量和设施供给数据，并用实地体验评估模型偏差。')

# 12 close
s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=rgb(INK)
img(s,'A1_行政区_全市.png',8.15,.25,4.4,6.95)
shape(s,MSO_SHAPE.PARALLELOGRAM,8.0,.3,4.8,6.75,GREEN,None,28)
rect(s,.72,.85,.12,5.35,ORANGE)
txt(s,'让城市路网\n成为更好的跑步空间',1.08,1.24,7.5,1.5,34,BG,True)
txt(s,'城市慢跑 / 慢骑环境适宜性评价与路线推荐',1.12,3.4,6.3,.42,18,MINT,True)
txt(s,'以武汉为例  ·  欢迎提问与指正',1.13,4.18,5.5,.36,15,BG)
txt(s,'OSM  /  SRTM  /  ESA WorldCover  /  高德 POI  /  CHAP',1.12,6.42,7.0,.28,10,MINT,False,FONT2)
note(s,'我们的工作到这里，欢迎老师和同学提问与指正。')

prs.save(OUT)
print(OUT)
