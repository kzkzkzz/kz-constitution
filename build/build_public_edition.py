#!/usr/bin/env python3
"""从公开底本生成合订本、来源索引与校验清单；不读取原工作档案。"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf as fitz
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.build'
OUT = ROOT / 'editions'
EDITION = '公开版第一版'
DATE = '2026-10-26'
PDF_NAME = 'The_kz_Constitution_Public_Edition_1.pdf'
AI_NAME = 'The_kz_Constitution_AI_Execution_Public_Edition_1.md'

SOURCES = [
    ('D1', 'DCGI 理由档案', 'sources/DCGI/DCGI_v0.3.tex', 'tex'),
    ('D2', 'DCGI 当前执行文本', 'sources/DCGI/DCGI_v0.3_execution.txt', 'txt'),
    ('V1', '数学论文 v5 审查法', 'sources/v5/Mathematical_Paper_v5_Audit_Method.tex', 'tex'),
    ('V2', 'v5 当前执行文本', 'sources/v5/v5_execution.txt', 'txt'),
    ('V3', '作者风格配置', 'sources/v5/v5_author_style_profile.txt', 'txt'),
    ('V4', 'AF-by-discrete 项目配置', 'sources/v5/v5_AF_by_discrete_project_profile.txt', 'txt'),
    ('V5', '单篇论文冻结清单模板', 'sources/v5/v5_freeze_manifest_template.txt', 'txt'),
    ('J1', '期刊选择宪法', 'sources/Journal_Selection/Journal_Selection_Constitution_v0_2_1.md', 'md'),
    ('J2', '期刊选择执行协议', 'sources/Journal_Selection/Journal_Selection_Execution_v0_2_1.md', 'md'),
    ('S1', '论文压力测试宪法', 'sources/Stress_Test/Adversarial_Paper_Stress_Test_Constitution_v0_3.md', 'md'),
    ('S2', '论文压力测试执行协议', 'sources/Stress_Test/Adversarial_Paper_Stress_Test_Execution_v0_3.md', 'md'),
    ('A1', '执行澄清与首次阅读简报', 'sources/Compilation/A1_Execution_Clarifications_Conversation_2026-10-20.md', 'md'),
]

GROUPS = [
    ('第一编｜DCGI · 闭依开生法', ['D1', 'D2'],
     '理由档案保留思想前史、数学判例与规则资格。实际协作采用当前独立执行文本。档案中保留的历史执行说明不替代 D2。'),
    ('第二编｜v5 · 文本、配置与冻结', ['V1', 'V2', 'V3', 'V4', 'V5'],
     'v5 接收已经取得资格的数学与事实判断，决定这些判断怎样进入论文。作者风格、项目配置和单篇冻结模板各有自己的适用范围。'),
    ('第三编｜期刊选择', ['J1', 'J2'],
     '本编保留期刊选择的规范与执行程序。作者当前的排除项、经历记录和个别投稿资料在每次应用时另行提供。'),
    ('第四编｜论文压力测试', ['S1', 'S2'],
     '本编在当前任务接受数学正确性的前提下检验不利阅读及其理由。数学疑点返回 DCGI，获准的文字修改返回 v5，期刊问题返回第三编。'),
    ('附录｜执行澄清', ['A1'],
     '本附录保留原有执行澄清，区分未接触既有讨论的 AI 阅读者与独立的人类审稿人，并保留首次阅读简报。'),
]

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def source_records():
    return [dict(id=i, title=t, path=p, format=f,
                 bytes=(ROOT/p).stat().st_size,
                 sha256=sha((ROOT/p).read_bytes())) for i,t,p,f in SOURCES]

def write_ai(records):
    by_id = {r['id']: r for r in records}
    text = '''# The kz Constitution

**AI 执行合订本｜公开版第一版｜2026-10-26｜依据 R5.1 整理**

## 组织说明

本文件汇集 DCGI、v5、期刊选择与论文压力测试的当前执行入口。底本之间保持原有职责边界，按任务调用有关部分。下列来源边界内的文字按公开底本逐字收录，保留各章原来的语言、术语与状态限定。

### 语言的形成历史

作者的哲学与心理学输入使用中文，数学输入使用英文。这一形成过程保留在各章的语言中：中文章节保持中文，英文章节保持英文，原有中英混用也予保留。目录、导读、版本说明及合订本的组织文字使用中文。

### 使用边界与来源

DCGI 判断数学与事实是否成立；v5 决定已取得资格的判断怎样进入论文；期刊选择处理发表路径；压力测试检验有依据的不利阅读及其接受风险。作者风格配置不是普遍写作规范，项目配置只适用于指定项目，冻结模板本身不宣告任何具体论文已经冻结。

完整的 DCGI 与 v5 理由档案见人类阅读合订本及公开源文件。本执行合订本不替代它们。私人的期刊经历画像、具名编辑事件和历史源包不随本版分发。使用者有相关记录时另行提供；未提供的事实保持未知。

S2 原执行文件保留其历史 Draft v0.3 标记；该底本的采纳记录属于 2026-10-20 的原工作版本。本公开版的整理状态见 RELEASE.md。保留历史标记不产生新规则，也不扩大文件的权限。A1 是原有执行澄清。

来源文件、字节数及校验值见 SOURCE_MAP.json 与 AI_SOURCE_BLOCKS.json。公开整理不构成对数学结论、文献优先性或现实编辑情况的重新认证。

## 导航

'''
    for k,(title,ids,note) in enumerate(GROUPS,1):
        text += f'- [{title}](#kz-part-{k})\n'
    embedded=[]
    for k,(title,ids,note) in enumerate(GROUPS,1):
        text += f'\n---\n\n<a id="kz-part-{k}"></a>\n\n## {title}\n\n{note}\n'
        for ident in ids:
            r=by_id[ident]
            if r['format']=='tex':
                continue
            raw=(ROOT/r['path']).read_bytes()
            if not raw.endswith(b'\n'):
                raise ValueError(f'底本须以换行结束：{r["path"]}')
            text += f'\n### {ident}｜{r["title"]}\n\n来源：`{r["path"]}`。\n\n'
            text += f'<!-- KZ-SOURCE-BEGIN {ident} bytes={len(raw)} sha256={sha(raw)} -->\n'
            text += raw.decode('utf-8')
            text += f'<!-- KZ-SOURCE-END {ident} -->\n'
            embedded.append(r)
    text += '\n---\n\n## 版本与完整性\n\n本文件由公开底本生成。修改底本后应重新生成合订本与校验清单；不在生成文件中维护另一份平行规则。公开版保留的方法论资格、作者选择与适用范围，以各底本的明确说明为准。\n'
    (OUT/AI_NAME).write_text(text,encoding='utf-8')
    (ROOT/'AI_SOURCE_BLOCKS.json').write_text(json.dumps(
        {'edition':EDITION,'date':DATE,'说明':'本表记录 AI 合订本逐字收录的十个公开来源区块。','blocks':embedded},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # 每个边界内的字节必须与对应底本相同。
    for r in embedded:
        start=f'<!-- KZ-SOURCE-BEGIN {r["id"]} bytes={r["bytes"]} sha256={r["sha256"]} -->\n'
        block=text.split(start,1)[1].split(f'<!-- KZ-SOURCE-END {r["id"]} -->',1)[0].encode('utf-8')
        if block!=(ROOT/r['path']).read_bytes():
            raise ValueError(f'来源区块不一致：{r["id"]}')

def esc(s: str) -> str:
    mapping={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','%':r'\%','&':r'\&',
             '$':r'\$','#':r'\#','_':r'\_','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(mapping.get(c,c) for c in s)

PREAMBLE = r'''\documentclass[UTF8,fontset=none,11pt]{ctexart}
\usepackage[a4paper,left=25mm,right=25mm,top=25mm,bottom=25mm,headheight=16pt]{geometry}
\usepackage{fontspec}
\IfFontExistsTF{Noto Serif CJK SC}{
 \setCJKmainfont{Noto Serif CJK SC}[BoldFont={Noto Serif CJK SC Bold},ItalicFont={Noto Serif CJK SC}]
 \setCJKsansfont{Noto Sans CJK SC}[BoldFont={Noto Sans CJK SC Bold}]
 \setCJKmonofont{Noto Sans CJK SC}
}{
 \setCJKmainfont{FandolSong-Regular}[Extension=.otf,BoldFont=FandolSong-Bold,ItalicFont=FandolKai-Regular]
 \setCJKsansfont{FandolHei-Regular}[Extension=.otf,BoldFont=FandolHei-Bold]
 \setCJKmonofont{FandolFang-Regular}[Extension=.otf]
}
\setmainfont{lmroman10-regular.otf}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]
\setsansfont{lmsans10-regular.otf}[BoldFont=lmsans10-bold.otf,ItalicFont=lmsans10-oblique.otf]
\setmonofont{lmmono10-regular.otf}[Scale=0.91]
\usepackage{amsmath,amssymb,booktabs,longtable,array,calc,enumitem,xcolor,xurl,fancyhdr,needspace,fvextra}
\DefineVerbatimEnvironment{verbatim}{Verbatim}{fontsize=\small,breaklines=true,breakanywhere=true}
\definecolor{ink}{HTML}{263B4B}
\definecolor{muted}{HTML}{61717B}
\definecolor{gold}{HTML}{A68452}
\usepackage[unicode,colorlinks=true,linkcolor=ink,urlcolor=ink]{hyperref}
\usepackage{bookmark}
\hypersetup{pdfauthor={Zheng Kuang},pdftitle={The kz Constitution — 公开版第一版}}
\ctexset{section={format=\Large\sffamily\bfseries\color{ink}},subsection={format=\large\sffamily\bfseries\color{ink}},subsubsection={format=\normalsize\sffamily\bfseries\color{ink}}}
\setcounter{secnumdepth}{0}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.48em}
\linespread{1.13}
\setlength{\emergencystretch}{3em}
\setlist{leftmargin=1.8em,itemsep=0.25em,topsep=0.35em}
\providecommand{\tightlist}{\setlength{\itemsep}{0.1em}\setlength{\parskip}{0pt}}
\providecommand{\passthrough}[1]{#1}
\providecommand{\pandocbounded}[1]{#1}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small\sffamily\color{muted}The kz Constitution}
\fancyhead[R]{\small\sffamily\color{muted}公开版第一版}
\fancyfoot[C]{\small\color{muted}\thepage}
\renewcommand{\headrulewidth}{0.3pt}
\clubpenalty=10000\widowpenalty=10000\raggedbottom
\begin{document}
'''

def unicode_math(body):
    for ch,tex in {'→':r'\ensuremath{\rightarrow}', '⇒':r'\ensuremath{\Rightarrow}',
                   '↔':r'\ensuremath{\leftrightarrow}', '≤':r'\ensuremath{\leq}',
                   '≥':r'\ensuremath{\geq}', '≠':r'\ensuremath{\neq}',
                   '−':r'\ensuremath{-}'}.items():
        body=body.replace(ch,tex)
    return body

def run(cmd, cwd, log_name):
    p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (cwd/log_name).write_text(p.stdout,encoding='utf-8')
    if p.returncode:
        raise RuntimeError(f'构建失败：{cmd[0]}；日志 {cwd/log_name}\n{p.stdout[-2500:]}')
    return p.stdout

def latex_compile(tex_path, folder, passes=2):
    folder.mkdir(parents=True,exist_ok=True)
    for j in range(passes):
        run(['xelatex','-no-pdf','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',
             '-output-directory='+str(folder),str(tex_path)],folder,f'run{j+1}.stdout')
    target=folder/(tex_path.stem+'.pdf')
    run(['xdvipdfmx','-o',str(target),str(folder/(tex_path.stem+'.xdv'))],folder,'xdvipdfmx.stdout')
    # 引擎退出状态之外，再确认 PDF 已完整写出。
    data=target.read_bytes()
    if not PdfReader(io.BytesIO(data)).pages:
        raise RuntimeError(f'生成的 PDF 没有页面：{target}')
    return data

def write_latex_pdf(key, body, title=None):
    folder=WORK/key
    folder.mkdir(parents=True,exist_ok=True)
    tex=folder/(key+'.tex')
    prefix=''
    if title:
        prefix=r'\section*{'+esc(title)+'}\n'
    tex.write_text(PREAMBLE+prefix+unicode_math(body)+'\n\\end{document}\n',encoding='utf-8')
    return latex_compile(tex,folder)

def plain_body(text):
    result=[]
    bullet=False
    for line in text.splitlines():
        if line.startswith('- '):
            if not bullet:
                result.append(r'\begin{itemize}')
                bullet=True
            result.append(r'\item '+esc(line[2:]))
            continue
        if bullet:
            result.append(r'\end{itemize}')
            bullet=False
        if not line.strip():
            result.append('')
        elif len(line)<45 and not re.match(r'^\d+[.、]',line) and not line.startswith(('Status:', 'Date:', 'Version:')):
            result.append(r'\Needspace{3\baselineskip}\textbf{'+esc(line)+r'}\par')
        else:
            result.append(esc(line)+r'\par')
    if bullet:
        result.append(r'\end{itemize}')
    return '\n'.join(result)

def build_source(entry):
    ident,title,path,fmt=entry
    src=ROOT/path
    folder=WORK/ident
    folder.mkdir(parents=True,exist_ok=True)
    if fmt=='tex':
        # 排版适配只作用于中间文件，公开底本的文字与字节保持独立。
        native=src.read_text(encoding='utf-8')
        native=re.sub(r'(?m)^\\begin\{tabularx\}',lambda m:r'\noindent'+m.group(0),native)
        if ident=='D1':
            # 保持第四条的资格说明与其正文同页，避免单独留下两行。
            native=native.replace('当方法开始遮住对象，至简原则要求停止那一套操作，',
                                  r'\enlargethispage{2\baselineskip}'+'\n'+'当方法开始遮住对象，至简原则要求停止那一套操作，',1)
        native=native.replace(r'\begin{document}',
            r'\setlength{\headheight}{16pt}'+'\n'+
            r'\IfFontExistsTF{Noto Sans CJK SC}{\setCJKmonofont{Noto Sans CJK SC}}{\setCJKmonofont{FandolFang-Regular}[Extension=.otf]}'+'\n'+
            r'\begin{document}',1)
        if ident=='V1':
            native=native.replace('Extension=.otf,BoldFont=FandolSong-Bold]',
                                  'Extension=.otf,BoldFont=FandolSong-Bold,ItalicFont=FandolKai-Regular]')
        generated=folder/src.name
        generated.write_text(native,encoding='utf-8')
        pdf=latex_compile(generated,folder,passes=3)
    else:
        pre=r'{\small\color{muted}来源：\path{'+path+r'}}\par\medskip'+'\n'
        if fmt=='md':
            body=run(['pandoc',str(src),'-f','markdown','-t','latex','--wrap=none','--no-highlight'],folder,'pandoc.stdout')
        else:
            body=plain_body(src.read_text(encoding='utf-8'))
        pdf=write_latex_pdf(ident,pre+body,title=f'{ident}｜{title}')
    return ident,pdf

def cover_pdf():
    body=r'''\thispagestyle{empty}
\vspace*{18mm}
{\sffamily\color{muted}\large 研究方法与协作规则}\par
\vspace{9mm}{\color{gold}\rule{25mm}{1.2pt}}\par\vspace{12mm}
{\fontsize{32}{40}\selectfont\sffamily\bfseries\color{ink}The kz Constitution}\par
\vspace{9mm}{\LARGE 公开版第一版}\par
\vspace{5mm}{\large 依据 R5.1 整理 · 2026 年 10 月 26 日}\par
\vspace{15mm}{\large 匡正\quad Zheng Kuang}\par
\vfill
{\large\sffamily\bfseries\color{ink}语言与形成历史}\par
作者的哲学与心理学输入使用中文，数学输入使用英文。本合订本保留各章形成时的语言与原有中英混用。目录、导读和版本说明使用中文。
\medskip
本书保留 DCGI 与 v5 的完整理由档案，以及期刊选择和论文压力测试的规范与执行文本。私人经历记录与历史源包另存于原工作档案。本 PDF 不嵌入附件。
\medskip
底本各自保留内部页码；下页目录和 PDF 书签使用合订本的总页序号。版本及来源说明见公开仓库中的 \path{RELEASE.md} 与 \path{SOURCE_MAP.json}。
\vspace*{6mm}
'''
    return write_latex_pdf('cover',body)

def divider_pdf(k,title,ids,note):
    names={i:t for i,t,p,f in SOURCES}
    body=r'\thispagestyle{empty}\vspace*{28mm}{\color{gold}\rule{25mm}{1.1pt}}\par\vspace{10mm}'+'\n'
    body+=r'{\fontsize{25}{33}\selectfont\sffamily\bfseries\color{ink}'+esc(title)+r'}\par\vspace{15mm}'+'\n'
    body+=esc(note)+r'\par\vspace{10mm}'+'\n'
    for ident in ids:
        body+=r'\textbf{'+ident+r'}\quad '+esc(names[ident])+r'\par\smallskip'+'\n'
    if k==4:
        body+=r'\vfill\small\color{muted}S2 保留原执行文件的历史 Draft v0.3 标记。该底本已在原工作版本于 2026-10-20 采纳；本公开版的整理状态见 RELEASE.md。具名案例登记簿不随本版分发。'+'\n'
    return write_latex_pdf('part'+str(k),body)

def toc_pdf(rows):
    body=r'\section*{目录}\small 总页序号按本合订本从封面起连续计算。\par\medskip\normalsize'+'\n'
    for level,title,page in rows:
        if level==0:
            body+=r'\Needspace{6\baselineskip}\vspace{5mm}\textbf{'+esc(title)+r'}\hfill '+str(page)+r'\par'+'\n'
        else:
            body+=r'\hspace*{1em}'+esc(title)+r'\hfill '+str(page)+r'\par'+'\n'
    return write_latex_pdf('contents',body)

def build_volume(parts):
    cover=cover_pdf()
    cover_n=len(PdfReader(io.BytesIO(cover)).pages)
    dividers={k:divider_pdf(k,title,ids,note) for k,(title,ids,note) in enumerate(GROUPS,1)}
    names={i:t for i,t,p,f in SOURCES}
    toc_n=2
    for _ in range(3):
        cursor=cover_n+toc_n
        rows=[]
        sequence=[]
        for k,(title,ids,note) in enumerate(GROUPS,1):
            rows.append((0,title,cursor+1))
            sequence.append((0,title,dividers[k]))
            cursor+=len(PdfReader(io.BytesIO(dividers[k])).pages)
            for ident in ids:
                label=ident+'｜'+names[ident]
                rows.append((1,label,cursor+1))
                sequence.append((1,label,parts[ident]))
                cursor+=len(PdfReader(io.BytesIO(parts[ident])).pages)
        toc=toc_pdf(rows)
        actual=len(PdfReader(io.BytesIO(toc)).pages)
        if actual==toc_n:
            break
        toc_n=actual
    else:
        raise RuntimeError('目录分页未收敛。')
    writer=fitz.open()
    bookmarks=[]

    def append_pdf(pdf):
        source=fitz.open(stream=pdf,filetype='pdf')
        reference=PdfReader(io.BytesIO(pdf))
        destinations=reference.named_destinations
        # 各底本可能重用同一目的地名称；合订前转换为底本内的明确页地址。
        for page in source:
            for link in page.get_links():
                name=link.get('nameddest')
                if name and name in destinations:
                    dest=destinations[name]
                    page_no=reference.get_destination_page_number(dest)
                    point=fitz.Point(float(dest.get('/Left') or 0),float(dest.get('/Top') or 0))
                    point=point*source[page_no].transformation_matrix
                    page.update_link({'kind':fitz.LINK_GOTO,'xref':link['xref'],
                                      'from':link['from'],'page':page_no,'to':point})
        source=fitz.open(stream=source.tobytes(),filetype='pdf')
        writer.insert_pdf(source,links=True,annots=True)

    append_pdf(cover)
    bookmarks.append([1,'封面与编写说明',1])
    append_pdf(toc)
    bookmarks.append([1,'目录',cover_n+1])
    for level,title,pdf in sequence:
        start=len(writer)
        if level==0:
            bookmarks.append([1,title,start+1])
            append_pdf(pdf)
        else:
            bookmarks.append([2,title,start+1])
            append_pdf(pdf)
            with fitz.open(stream=pdf,filetype='pdf') as source:
                for depth,label,p in source.get_toc():
                    if p>0:
                        bookmarks.append([2+depth,label,start+p])
    writer.set_toc(bookmarks)
    # 主目录的条目也可直接跳转；原底本内的目录链接仍分别保留。
    for page_no in range(cover_n,cover_n+toc_n):
        page=writer[page_no]
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                label=re.sub(r'\s+','', ''.join(s['text'] for s in line['spans']))
                for _,title,dest_page in rows:
                    if re.sub(r'\s+','',title) in label:
                        rect=fitz.Rect(line['bbox'])
                        rect.x1=page.rect.width-60
                        page.insert_link({'kind':fitz.LINK_GOTO,'from':rect,
                                          'page':dest_page-1,'to':fitz.Point(0,0)})
    writer.set_metadata({'title':'The kz Constitution — 公开版第一版',
                         'author':'Zheng Kuang',
                         'subject':'DCGI、v5、期刊选择与论文压力测试；依据 R5.1 整理的公开版',
                         'keywords':'DCGI, 闭依开生法, v5, 数学论文, 期刊选择, 压力测试',
                         'creator':'XeLaTeX / Pandoc / PyMuPDF'})
    writer.set_pagemode('UseOutlines')
    target=OUT/PDF_NAME
    writer.save(target,garbage=4,deflate=True)
    writer.close()
    check=PdfReader(target)
    if len(check.attachments):
        raise ValueError('公开 PDF 不应含嵌入附件。')
    if len(check.pages)!=cursor:
        raise ValueError('总页数与目录计算不一致。')
    (WORK/'volume_map.json').write_text(json.dumps({'pages':len(check.pages),'contents':rows},ensure_ascii=False,indent=2)+'\n')
    return len(check.pages)

def write_manifests(records):
    (ROOT/'SOURCE_MAP.json').write_text(json.dumps(
        {'edition':EDITION,'date':DATE,'说明':'本表仅列公开底本；历史原件不随公开版分发。','sources':records},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files=[]
    for p in ROOT.rglob('*'):
        if not p.is_file():
            continue
        rel=p.relative_to(ROOT)
        if any(x in {'.build','.git','__pycache__'} for x in rel.parts):
            continue
        if rel.as_posix()=='SHA256SUMS.txt' or p.suffix=='.pyc':
            continue
        files.append((rel.as_posix(),sha(p.read_bytes())))
    (ROOT/'SHA256SUMS.txt').write_text(''.join(f'{h}  {p}\n' for p,h in sorted(files)),encoding='utf-8')

def main():
    global WORK
    for cmd in ['xelatex','xdvipdfmx','pandoc']:
        if shutil.which(cmd) is None:
            raise SystemExit(f'缺少构建工具：{cmd}')
    WORK.mkdir(exist_ok=True)
    # 每次完整构建采用新的中间目录，避免旧辅助文件影响当前输出。
    WORK=Path(tempfile.mkdtemp(prefix='run-',dir=WORK))
    OUT.mkdir(exist_ok=True)
    records=source_records()
    write_ai(records)
    # 按来源顺序排版，避免多个 XeLaTeX 进程竞争字体缓存。
    parts=dict(build_source(entry) for entry in SOURCES)
    pages=build_volume(parts)
    write_manifests(records)
    print(json.dumps({'公开版':EDITION,'页数':pages,'AI来源区块':10,'底本数量':len(records),'PDF':str(OUT/PDF_NAME),'AI合订本':str(OUT/AI_NAME),'中间目录':str(WORK)},ensure_ascii=False))

if __name__=='__main__':
    main()
