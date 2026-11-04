from pptx import Presentation

p = Presentation(r"E:\MyProject\等时圈交通可达性分析系统\presentation\项目展示-runroute-20261030.pptx")

for idx in (7, 8):
    s = p.slides[idx]
    print("===== slide", idx + 1, "=====")

    def walk(shapes, d=0):
        for sh in shapes:
            t = sh.top / 914400 if sh.top is not None else -1
            l = sh.left / 914400 if sh.left is not None else -1
            w = sh.width / 914400 if sh.width is not None else -1
            h = sh.height / 914400 if sh.height is not None else -1
            txt = sh.text_frame.text[:24].replace(chr(11), " ") if sh.has_text_frame else ""
            print("%s%-3s %-18s L%6.2f T%6.2f W%6.2f H%6.2f %r" % ("  " * d, sh.shape_type, sh.name, l, t, w, h, txt))
            if sh.shape_type == 6:
                walk(sh.shapes, d + 1)

    walk(s.shapes)
