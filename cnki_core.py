# -*- coding: utf-8 -*-
"""知网浏览器批量下载核心（供 GUI main_ui.py 调用，也可独立使用）

依赖：playwright（pip install playwright）+ 系统 Edge 浏览器
凭证：同目录 cnki_cookie.txt（浏览器登录 www.cnki.net 后 F12 复制的 Cookie 值）

用法（独立）:
  from cnki_core import parse_list, run_batch
  rows = parse_list('中文文献清单.txt')
  ok, fails = run_batch(rows, 'save_dir', callback=print)
"""
import os
import re
import time
import datetime
from urllib.parse import quote

BASE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE, 'cnki_cookie.txt')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def parse_list(path):
    """解析清单：每行 题名<TAB>作者<TAB>年份，返回 [(title, author, year)]"""
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding='utf-8', errors='replace'):
        parts = line.rstrip('\n').split('\t')
        if parts[0].strip():
            rows.append((parts[0].strip(),
                         parts[1].strip() if len(parts) > 1 else '',
                         parts[2].strip() if len(parts) > 2 else ''))
    return rows


def _load_cookie():
    if not os.path.exists(COOKIE_FILE):
        return ''
    ck = open(COOKIE_FILE, encoding='utf-8').read().strip()
    if ck.lower().startswith('cookie:'):
        ck = ck.split(':', 1)[1].strip()
    return ck


def _inject_cookie(ctx, ck):
    for part in ck.split(';'):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition('=')
        try:
            ctx.add_cookies([{'name': k.strip(), 'value': v.strip(),
                              'domain': '.cnki.net', 'path': '/'}])
        except Exception:
            pass


SEARCH_ATTEMPTS = 3
_EMPTY_MARKERS = ('抱歉', '无数据')


def _page_says_no_result(pg):
    """CNKI 查无结果时渲染「抱歉/无数据」提示，而不是一张空结果表"""
    try:
        text = pg.inner_text('body')
    except Exception:
        return False
    return any(m in text for m in _EMPTY_MARKERS)


def _search_rows(pg, title):
    """检索题名，返回 (结果行列表, 错误串)。

    检索页偶发渲染失败（同一篇真论文可能这次 1 秒出结果、下次等不到表），所以重试几次；
    同时把「页面没加载出来」和「确实没有这个题名」分开报——前者该重试，后者该改清单。
    """
    url = ('https://kns.cnki.net/kns8s/defaultresult/index?kw=%s&korder=SU'
           % quote(title))
    last_err = ''
    for attempt in range(SEARCH_ATTEMPTS):
        if attempt:
            time.sleep(2)
        try:
            pg.goto(url, timeout=40000)
        except Exception as e:
            last_err = '检索页加载失败:' + str(e)[:50]
            continue
        try:
            pg.wait_for_selector('.result-table-list tbody tr', timeout=15000)
        except Exception:
            if _page_says_no_result(pg):
                return [], '未检索到该题名'
            last_err = '检索页加载失败:结果表未渲染'
            continue
        pg.wait_for_timeout(1500)
        return pg.query_selector_all('.result-table-list tbody tr'), ''
    return [], last_err or '检索页加载失败'


def _download_one(pg, title, out_path):
    """单篇：检索 -> 详情页 -> PDF下载 -> %PDF 校验落盘。返回 (ok, msg)"""
    rows, err = _search_rows(pg, title)
    if err:
        return False, err
    if not rows:
        return False, '未检索到该题名'
    row = rows[0]
    link = row.query_selector('td.name a, a[href*="kcms2/article"], a[href*="/detail"]')
    if not link:
        return False, '无详情链接'
    href = link.get_attribute('href')
    if not href or href.startswith('javascript'):
        return False, '详情链接无效'
    if href.startswith('/'):
        href = 'https://kns.cnki.net' + href
    try:
        pg.goto(href, timeout=40000)
        pg.wait_for_timeout(4000)
    except Exception as e:
        return False, '详情页异常:' + str(e)[:60]
    # 期刊文章用 a#pdfDown；学位论文等页面用文本匹配「PDF下载」
    pdf_btn = pg.query_selector('a#pdfDown')
    if not pdf_btn:
        pdf_btn = pg.query_selector('a[href*="bar.cnki.net"]:has-text("PDF下载")')
    if not pdf_btn:
        return False, '详情页无PDF下载按钮'
    try:
        with pg.expect_download(timeout=90000) as dl_info:
            pdf_btn.click()
        with open(dl_info.value.path(), 'rb') as fh:
            data = fh.read()
    except Exception as e:
        return False, '下载异常:' + str(e)[:60]
    if data[:4] != b'%PDF':
        return False, '非PDF(%.0fKB)' % (len(data) / 1024)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(data)
    return True, 'ok'


def run_batch(rows, save_dir, callback=None, log=None, headless=True, gap=2):
    """批量下载知网 PDF。

    rows: parse_list 的输出 [(title, author, year), ...]
    callback(i, total, status, fname, err)  status: ok / fail / exist
    log(msg): 一行提示输出
    返回 (ok_cnt, fail_list)；失败清单自动落盘 _tools 目录
    """
    assert rows, '清单为空'
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError('缺少 playwright，请运行: pip install playwright')

    os.makedirs(save_dir, exist_ok=True)
    ck = _load_cookie()
    if not ck:
        raise RuntimeError('缺少 cnki_cookie.txt（知网登录凭证）。请浏览器登录知网后 F12 复制 Cookie 保存到该文件')

    total = len(rows)
    ok_cnt = 0
    fail_list = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=headless)
        ctx = browser.new_context(user_agent=UA)
        _inject_cookie(ctx, ck)
        pg = ctx.new_page()
        for i, (title, author, year) in enumerate(rows):
            fname = _ILLEGAL.sub('', title).strip() or 'untitled_%d' % i
            out = os.path.join(save_dir, fname + '.pdf')
            if log:
                log('[%d/%d] %s' % (i + 1, total, title[:45]))
            # 已有真 PDF 跳过
            if os.path.exists(out):
                with open(out, 'rb') as fh:
                    head = fh.read(4)
                if head == b'%PDF':
                    ok_cnt += 1
                    if callback:
                        callback(i, total, 'exist', out)
                    continue
                os.remove(out)
            try:
                ok, msg = _download_one(pg, title, out)
            except Exception as e:
                ok, msg = False, '异常:' + str(e)[:80]
            if ok:
                ok_cnt += 1
                if callback:
                    callback(i, total, 'ok', out)
            else:
                fail_list.append((title, msg))
                if callback:
                    callback(i, total, 'fail', out, msg)
                if log:
                    log('  FAIL %s' % msg)
            time.sleep(gap)
        browser.close()

    if fail_list:
        try:
            fp = os.path.join(BASE, '知网失败清单_%s.txt'
                              % datetime.datetime.now().strftime('%m%d_%H%M'))
            with open(fp, 'w', encoding='utf-8') as f:
                for t, msg in fail_list:
                    f.write('%s\t%s\n' % (t, msg))
            if log:
                log('失败清单已保存: %s' % fp)
        except Exception:
            pass
    return ok_cnt, fail_list