# -*- coding: utf-8 -*-
# @Time    : 2021/10/12 22:49 
# @Author  : Yong Cao
# @Email   : yongcao_epic@hust.edu.cn
import os
import re
from datetime import date


_rstr = r"[\=\(\)\,\/\\\:\*\?\?\"\<\>\|\'']"


def _clean_name(title):
    """清理标题中的非法文件名字符"""
    title = re.sub(r'\s+', ' ', title).strip()  # 换行/多空格归一为单空格
    cleaned = re.sub(_rstr, '', title).strip()
    if len(cleaned) > 200:  # 防止文件路径超过Windows 260字符限制
        cleaned = cleaned[:200].rstrip()
    return cleaned


def _parse_bibtex(content):
    """BibTeX: @article{...} 条目，提取 Title / DOI"""
    entries = []
    for block in content.split('@article{')[1:]:
        m_t = re.search(r'Title\s*=\s*\{([^}]+)\}', block)
        m_d = re.search(r'DOI\s*=\s*\{([^}]+)\}', block, re.I)
        if m_t:
            entries.append({'title': m_t.group(1).strip(),
                            'doi': m_d.group(1).strip() if m_d else ''})
    return entries


def _parse_ris(content):
    """RIS: TY  - / TI  - / DO  - 字段"""
    entries, cur = [], {}
    for lin in content.split('\n'):
        s = lin.rstrip('\r\n')
        m = re.match(r'^([A-Z0-9]{2})\s{2}-\s(.*)$', s)
        if s.startswith('TY  - '):
            if cur.get('title') and cur.get('doi'):
                entries.append(cur)
            cur = {}
        elif m:
            k, v = m.group(1), m.group(2).strip()
            if k == 'TI' and v:
                cur['title'] = v
            elif k == 'DO' and v:
                cur['doi'] = v
    if cur.get('title') and cur.get('doi'):
        entries.append(cur)
    return entries


def _parse_ne(content):
    """NE 题录导出格式: 题录类型 / 标题 / DOI 等 K:V 行（也可解析其他 K:V 格式）"""
    entries, cur = [], {}
    for lin in content.split('\n'):
        s = lin.strip()
        if not s:
            if cur.get('title'):
                entries.append(cur)
            cur = {}
            continue
        m = re.match(r'^([^:：]{1,10})[:：]\s*(.+)$', s)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if k in ('标题', 'Title', '题名') and v:
                cur['title'] = v
            elif k.upper() == 'DOI' and v:
                cur['doi'] = v
    if cur.get('title'):
        entries.append(cur)
    return entries


def _parse_endnote(content):
    """EndNote ENW: %T 标题 / %R DOI / %0 分隔条目"""
    entries, cur = [], {}
    for lin in content.split('\n'):
        s = lin.rstrip('\r\n')
        m = re.match(r'^%([A-Z0-9])\s+(.*)$', s)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if k == 'T' and v:
                cur['title'] = v
            elif k == 'R' and v and ('10.' in v or 'doi' in v.lower()):
                cur['doi'] = v
            elif k == '0' and cur.get('title'):
                if cur.get('doi'):
                    entries.append(cur)
                cur = {}
    if cur.get('title') and cur.get('doi'):
        entries.append(cur)
    return entries


def _parse_citation(content):
    """IEEE Citation（方法1原格式）: 引号标题行 + URL 行"""
    entries = []
    for block in content.split('\n\n'):
        lines = [l for l in block.split('\n') if l.strip()]
        if not lines:
            continue
        m_t = re.search(r'"([^"]+)"', lines[0])
        url_line = ''
        for l in lines:
            if l.strip().startswith('URL:'):
                url_line = l.strip()
                break
        if m_t and url_line:
            arnumber = url_line.replace("URL: http://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=", "").split("&")[0]
            url = "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=" + arnumber + "&ref="
            entries.append({'title': m_t.group(1).strip(), 'doi': '', 'url': url})
    return entries


def organize_info_by_txt(dst_dir, url_file, paper_name_with_year=None):
    """智能解析：自动识别 BibTeX / RIS / NE题录 / EndNote / IEEE Citation"""
    if not os.path.exists(url_file):
        return False, None
    with open(url_file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if '@article' in content:
        entries, fmt = _parse_bibtex(content), 'BibTeX'
    elif re.search(r'^TY\s{2}-', content, re.M):
        entries, fmt = _parse_ris(content), 'RIS'
    elif re.search(r'^%[A-Z0-9]\s', content, re.M):
        entries, fmt = _parse_endnote(content), 'EndNote'
    elif re.search(r'^题录类型[:：]', content, re.M):
        entries, fmt = _parse_ne(content), 'NE题录'
    else:
        entries, fmt = _parse_citation(content), 'IEEE Citation'

    paper_info = {}
    for i, e in enumerate(entries):
        if not e.get('title'):
            continue
        papername = _clean_name(e['title'])
        if paper_name_with_year:
            papername = '%d ' % date.today().year + papername
        papername = os.path.join(dst_dir, papername + '.pdf')
        paper_info[i] = {'name': papername, 'doi': e.get('doi', ''), 'url': e.get('url', '')}
    print('[organize] 格式=%s 条目=%d' % (fmt, len(paper_info)))
    return True, paper_info
